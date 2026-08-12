-- ============================================================
-- Esquema de Base de Datos - Sistema de Inventario Jugueteria
-- Modelo definitivo (personal, productos, ubicaciones, ventas,
-- detalle_ventas, proveedores, movimientos)
-- ============================================================

PRAGMA foreign_keys = ON;

-- -----------------------------------------------------
-- 1. PERSONAL (Administradores, Empleados, Cajeros)
-- Tabla de usuarios del sistema: login (pestana Personal/Usuarios) y
-- fuente de los selects de "Usuario" y "Aprobada por" en Ventas.
-- contrasena_hash se guarda siempre con hash (werkzeug), nunca en
-- texto plano. La fila semilla de "admin" queda con el placeholder
-- 'temporal' porque SQL puro no genera hashes; models/database.py
-- la reemplaza por el hash real de 'admin123' en el primer arranque.
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS personal (
    id_personal INTEGER PRIMARY KEY AUTOINCREMENT,
    nombres TEXT NOT NULL,
    apellido_paterno TEXT NOT NULL,
    apellido_materno TEXT,
    ci TEXT UNIQUE NOT NULL,
    telefono TEXT,
    usuario TEXT UNIQUE NOT NULL,
    contrasena_hash TEXT NOT NULL,
    rol TEXT NOT NULL CHECK(rol IN ('Super Admin', 'Admin', 'Empleado', 'Bodega')),
    estado INTEGER DEFAULT 1 CHECK(estado IN (0, 1))  -- 1 = Activo, 0 = Inactivo
);

-- -----------------------------------------------------
-- 2. UBICACIONES (lista desplegable controlada para Productos)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ubicaciones (
    id_ubicacion INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE
);

-- -----------------------------------------------------
-- 3. PRODUCTOS (Catalogo General con Tarifas y Ubicacion)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS productos (
    id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
    foto_url TEXT,
    nombre TEXT NOT NULL,
    -- codigo_1 NO es unico por si solo: el cliente confirmo que se repite
    -- entre productos distintos en su catalogo real. Lo que si identifica
    -- un producto de forma unica es la COMBINACION codigo_1 + codigo_2
    -- (ver el UNIQUE compuesto al final de la tabla, y
    -- productos_model.get_producto_por_codigo / guardar_o_actualizar_desde_excel,
    -- que ya matchean por el par completo).
    codigo_1 TEXT NOT NULL,
    codigo_2 TEXT,
    descripcion TEXT,
    marca TEXT,

    -- Esquema de precios
    precio_unidad_facturado REAL DEFAULT 0,   -- PUF
    precio_docena_facturado REAL DEFAULT 0,   -- PDF
    precio_paquete_facturado REAL DEFAULT 0,  -- PPF
    precio_paquete_neto REAL DEFAULT 0,       -- PPN
    precio_docena_neto REAL DEFAULT 0,        -- PDN
    precio_docena_comercial REAL DEFAULT 0,   -- PDC
    descuento_porcentaje REAL DEFAULT 0,
    incremento_porcentaje REAL DEFAULT 0,

    -- Presentacion y empaque
    pcs_paquete INTEGER DEFAULT 0,
    pcs_caja INTEGER DEFAULT 0,
    venta_fraccionada TEXT DEFAULT 'No' CHECK(venta_fraccionada IN ('Si', 'No')),

    -- Ubicacion y existencias
    id_ubicacion INTEGER REFERENCES ubicaciones(id_ubicacion),
    posicion TEXT,
    -- Puede quedar en 0 o mayor (piezas sueltas -> decimal, ej. venta
    -- fraccionada) o en NEGATIVO: negativo significa que se aprobo una
    -- venta por mas de lo que habia en tienda, y ese numero es lo que
    -- falta reponer desde el almacen (ver alerta en Inicio).
    cantidad REAL NOT NULL DEFAULT 0,

    -- Estado de negocio (Activo/Inactivo). "Agotado" NO se guarda aqui:
    -- se calcula en la aplicacion comparando cantidad <= 0 (0 o negativo,
    -- ver mas abajo), para evitar que quede desincronizado con el stock real.
    estado TEXT DEFAULT 'Activo' CHECK(estado IN ('Activo', 'Inactivo')),

    UNIQUE(codigo_1, codigo_2)
);

-- -----------------------------------------------------
-- 4. VENTAS (Cabecera de la transaccion)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS ventas (
    id_venta INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Codigo unico para que el cliente/administrador pueda buscar esta
    -- venta puntual (ej. VTA-20260808-6676). Se genera al crear la venta,
    -- ya en estado Pendiente (ver ventas_model.generar_codigo_venta).
    codigo_venta TEXT UNIQUE,

    id_personal_registro INTEGER NOT NULL REFERENCES personal(id_personal),
    ubicacion TEXT NOT NULL,   -- sucursal/punto de venta (ej. ORTIZ)

    cliente_nombre TEXT DEFAULT 'Publico General',  -- nombre y apellido del cliente
    cliente_ci TEXT,
    observaciones TEXT,

    -- Numero de serie de la factura escrita a mano y foto de esa factura
    -- (nombre de archivo en uploads/facturas, servido por una ruta con
    -- sesion, ver ventas_controller.factura_imagen), capturadas por la
    -- app movil al vender por QR. NULL en ventas creadas desde escritorio.
    numero_factura TEXT,
    foto_factura TEXT,

    estado TEXT DEFAULT 'Pendiente' CHECK(estado IN ('Pendiente', 'Aprobada', 'Rechazada')),
    id_personal_aprobador INTEGER REFERENCES personal(id_personal),

    fecha_venta TEXT DEFAULT (date('now', 'localtime')),
    hora_venta TEXT DEFAULT (time('now', 'localtime')),
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,   -- usado para orden FIFO
    fecha_resolucion TIMESTAMP,

    total REAL NOT NULL DEFAULT 0 CHECK(total >= 0)
);

-- -----------------------------------------------------
-- 5. DETALLE_VENTAS (una linea por cada producto en el carrito)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS detalle_ventas (
    id_detalle INTEGER PRIMARY KEY AUTOINCREMENT,
    id_venta INTEGER NOT NULL REFERENCES ventas(id_venta) ON DELETE CASCADE,
    id_producto INTEGER NOT NULL REFERENCES productos(id_producto),
    -- Piezas vendidas. Normalmente entero, pero puede ser decimal (ej. 7.5)
    -- cuando la linea se vendio en modo "pago por piezas" (unidad_venta != NULL).
    cantidad INTEGER NOT NULL CHECK(cantidad > 0),

    tipo_precio_aplicado TEXT NOT NULL CHECK(
        tipo_precio_aplicado IN ('PUF', 'PDF', 'PPF', 'PPN', 'PDN', 'PDC', 'PERSONALIZADO')
    ),
    -- Unidad de fraccionamiento elegida al vender "por piezas" (pieza suelta,
    -- cuarta, media, docena, paquete o caja). NULL = venta normal por tarifa
    -- completa (comportamiento de siempre, sin fraccionar).
    unidad_venta TEXT CHECK(unidad_venta IN ('pieza', 'cuarta', 'media', 'docena', 'paquete', 'caja')),
    precio_aplicado REAL NOT NULL CHECK(precio_aplicado >= 0),
    subtotal REAL NOT NULL CHECK(subtotal >= 0)
);

-- -----------------------------------------------------
-- 6. PROVEEDORES
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS proveedores (
    id_proveedor INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    contacto TEXT,
    telefono TEXT
);

-- -----------------------------------------------------
-- 7. MOVIMIENTOS (Kardex: entradas, salidas, garantias, devoluciones)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS movimientos (
    id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT,
    id_producto INTEGER NOT NULL REFERENCES productos(id_producto),
    id_personal INTEGER NOT NULL REFERENCES personal(id_personal),
    id_venta INTEGER REFERENCES ventas(id_venta) ON DELETE SET NULL,
    id_proveedor INTEGER REFERENCES proveedores(id_proveedor),

    tipo_movimiento TEXT NOT NULL CHECK(
        tipo_movimiento IN (
            'INGRESO_MERCADERIA',
            'SALIDA_VENTA',
            'GARANTIA_ENTRADA',
            'GARANTIA_BAJA',
            'DEVOLUCION_PROVEEDOR',
            'AJUSTE_INVENTARIO'
        )
    ),
    cantidad INTEGER NOT NULL,   -- positivo (+) entradas, negativo (-) salidas
    motivo_nota TEXT,
    fecha TEXT DEFAULT (datetime('now', 'localtime'))
);

-- -----------------------------------------------------
-- 8. ARCHIVOS_IMPORTADOS (Gestion de Archivos)
-- Registra, en orden de llegada, cada archivo Excel que el cliente
-- importa desde la pestana Productos. El archivo fisico se guarda en
-- uploads/importaciones (fuera de static/, servido por una ruta con
-- sesion) y aqui queda el historial consultable.
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS archivos_importados (
    id_archivo INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_original TEXT NOT NULL,
    nombre_guardado TEXT NOT NULL,
    id_personal INTEGER REFERENCES personal(id_personal),
    registros_procesados INTEGER NOT NULL DEFAULT 0,
    fecha_importacion TEXT DEFAULT (datetime('now', 'localtime'))
);

-- -----------------------------------------------------
-- INDICES
-- -----------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_personal_ci ON personal(ci);
CREATE INDEX IF NOT EXISTS idx_prod_codigo1 ON productos(codigo_1);
CREATE INDEX IF NOT EXISTS idx_prod_codigo2 ON productos(codigo_2);
CREATE INDEX IF NOT EXISTS idx_ventas_estado ON ventas(estado);
CREATE INDEX IF NOT EXISTS idx_mov_producto ON movimientos(id_producto);
CREATE INDEX IF NOT EXISTS idx_mov_venta ON movimientos(id_venta);

-- -----------------------------------------------------
-- DATOS SEMILLA
-- -----------------------------------------------------
INSERT OR IGNORE INTO ubicaciones (id_ubicacion, nombre) VALUES
    (1, 'Pasillo A'),
    (2, 'Pasillo B'),
    (3, 'Pasillo C'),
    (4, 'Bodega General'),
    (5, 'Estante 1'),
    (6, 'Estante 2');

-- Personal semilla: Yeraldin es solo un empleado de ejemplo para los
-- selects de Ventas. El usuario "admin" es la cuenta inicial del
-- sistema (usuario: admin / contrasena: admin123, rol Super Admin); el
-- administrador real debe cambiar esa contrasena o crear su propia
-- cuenta y eliminar/desactivar esta desde la pantalla de Usuarios.
INSERT OR IGNORE INTO personal (id_personal, nombres, apellido_paterno, apellido_materno, ci, telefono, usuario, contrasena_hash, rol, estado) VALUES
    (1, 'Yeraldin', 'Quispe', 'Mamani', '1111111', '70000001', 'yeraldin', 'temporal', 'Empleado', 1),
    (2, 'Admin', 'Sistema', NULL, '0000000', '70000000', 'admin', 'temporal', 'Super Admin', 1);
