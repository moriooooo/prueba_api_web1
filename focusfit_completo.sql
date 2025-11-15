CREATE DATABASE IF NOT EXISTS focusfit;
USE focusfit;

-- ==========================
-- TABLA: usuario
-- ==========================
CREATE TABLE usuario (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    correo VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    avatar VARCHAR(255) DEFAULT NULL,
    telefono VARCHAR(30) DEFAULT NULL,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    current_streak INT DEFAULT 0,           -- Racha actual
    longest_streak INT DEFAULT 0,           -- Racha más larga
    last_streak_date DATE DEFAULT NULL,     -- ✅ NUEVO: Fecha última evaluación
    racha_base_hoy INT DEFAULT 0           -- ✅ NUEVO: Valor referencia recálculos
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==========================
-- TABLA: rutina
-- ==========================
CREATE TABLE rutina (
    id_rutina INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    tipo ENUM('estudio', 'ejercicio') NOT NULL,
    duracion_horas INT DEFAULT 0,
    duracion_minutos INT DEFAULT 0,
    dias VARCHAR(100),                 -- Ej: "Lunes,Martes,Miércoles"
    horario TIME,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    id_usuario INT,
    FOREIGN KEY (id_usuario) REFERENCES usuario(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==========================
-- TABLA: rutina_item
-- ==========================
CREATE TABLE rutina_item (
    id_item INT AUTO_INCREMENT PRIMARY KEY,
    id_rutina INT NOT NULL,
    nombre_item VARCHAR(100) NOT NULL,
    series INT,
    repeticiones INT,
    tiempo INT,                        -- en minutos
    prioridad ENUM('alta','media','baja'),
    FOREIGN KEY (id_rutina) REFERENCES rutina(id_rutina) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==========================
-- TABLA: item_diario (CLAVE para el sistema de rachas)
-- ==========================
CREATE TABLE item_diario (
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_item INT NOT NULL,
    id_usuario INT NOT NULL,
    fecha DATE NOT NULL,
    completado BOOLEAN DEFAULT FALSE,
    completado_en DATETIME NULL,
    FOREIGN KEY (id_item) REFERENCES rutina_item(id_item) ON DELETE CASCADE,
    FOREIGN KEY (id_usuario) REFERENCES usuario(id) ON DELETE CASCADE,
    UNIQUE KEY unique_item_fecha (id_item, fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Índices para optimización
CREATE INDEX idx_item_diario_usuario_fecha ON item_diario (id_usuario, fecha);
CREATE INDEX idx_item_diario_completado ON item_diario (completado, fecha);

-- ==========================
-- TABLA: user_notifications (renombrada desde `notifications` para evitar conflictos)
-- ==========================
CREATE TABLE user_notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT,
    fecha_programada DATETIME,
    is_read TINYINT(1) DEFAULT 0,
    fecha_envio DATETIME NULL,
    tipo VARCHAR(50) DEFAULT 'recordatorio',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES usuario(id) ON DELETE CASCADE,
    INDEX (user_id),
    INDEX (is_read),
    INDEX (fecha_programada)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==========================
-- TABLA: contenido_admin
-- ==========================
CREATE TABLE contenido_admin (
    id INT AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(150),
    tipo_contenido ENUM('banner','mensaje_bienvenida','ayuda','rutina_destacada') NOT NULL,
    texto TEXT,
    url_imagen VARCHAR(255) NULL,
    activo BOOLEAN DEFAULT TRUE,
    programado_para DATETIME NULL,
    actualizado_por VARCHAR(100),
    actualizado_en DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==========================
-- TABLA: log_admin
-- ==========================
CREATE TABLE log_admin (
    id INT AUTO_INCREMENT PRIMARY KEY,
    admin_id VARCHAR(100) NOT NULL,
    accion VARCHAR(200) NOT NULL,
    detalles JSON,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==========================
-- DATOS DE PRUEBA (OPCIONAL)
-- ==========================

-- Usuario de prueba
INSERT INTO usuario (nombre, correo, password, current_streak, longest_streak) 
VALUES 
('Usuario Demo', 'demo@focusfit.com', '123456', 0, 0),
('Admin FocusFit', 'admin@focusfit.com', 'admin123', 0, 0);

-- Rutina de ejemplo
INSERT INTO rutina (nombre, tipo, duracion_horas, duracion_minutos, dias, horario, id_usuario) 
VALUES 
('Rutina Matutina', 'ejercicio', 1, 0, 'Lunes,Miércoles,Viernes', '07:00:00', 1),
('Estudio Programación', 'estudio', 2, 0, 'Lunes,Martes,Miércoles,Jueves,Viernes', '09:00:00', 1);

-- Items de rutina de ejemplo
INSERT INTO rutina_item (id_rutina, nombre_item, series, repeticiones, tiempo, prioridad) 
VALUES 
(1, 'Calentamiento', 1, 1, 10, 'alta'),
(1, 'Flexiones', 3, 15, 5, 'alta'),
(1, 'Abdominales', 3, 20, 10, 'media'),
(1, 'Estiramiento', 1, 1, 15, 'baja'),
(2, 'Revisar teoría', 1, 1, 30, 'alta'),
(2, 'Hacer ejercicios', 1, 1, 60, 'alta'),
(2, 'Proyecto personal', 1, 1, 30, 'media');


-- Tablas mínimas para panel admin
CREATE TABLE IF NOT EXISTS `admin` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `email` VARCHAR(255) NOT NULL UNIQUE,
  `password` VARCHAR(255) NOT NULL,
  `name` VARCHAR(255),
  `avatar` VARCHAR(255),
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `admin` (`email`, `password`, `name`, `avatar`)
VALUES (
  'evinava8@gmail.com',
  'pbkdf2:sha256:600000$03JXOoAOrewcT0Kv$5160c1d9f4285c71eaeaedcf3051567fdb6714dd907648998b3c06257250b640',
  'Administrador',
  NULL
);

CREATE TABLE IF NOT EXISTS `admin_content` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `type` VARCHAR(50) NOT NULL,
  `title` VARCHAR(255) NOT NULL,
  `body` TEXT,
  `image` VARCHAR(255),
  `created_by` VARCHAR(255),
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `updated_by` VARCHAR(255),
  `updated_at` DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
  
CREATE TABLE IF NOT EXISTS recommendations (
id INT AUTO_INCREMENT PRIMARY KEY,
title VARCHAR(255) NOT NULL,
summary TEXT,
body TEXT,
difficulty ENUM('facil','medio','dificil') DEFAULT 'medio',
tipo ENUM('estudio','ejercicio') DEFAULT 'ejercicio',
duration_minutes INT DEFAULT NULL,
image VARCHAR(255) DEFAULT NULL,
is_public TINYINT(1) DEFAULT 1,
created_by VARCHAR(100),
created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
updated_by VARCHAR(100),
updated_at DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_recommendations (
id INT AUTO_INCREMENT PRIMARY KEY,
user_id INT NOT NULL,
recommendation_id INT NOT NULL,
saved_at DATETIME DEFAULT CURRENT_TIMESTAMP,
FOREIGN KEY (user_id) REFERENCES usuario(id) ON DELETE CASCADE,
FOREIGN KEY (recommendation_id) REFERENCES recommendations(id) ON DELETE CASCADE,
UNIQUE KEY unique_user_recommendation (user_id, recommendation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- SQL additions for community posts and recommendations integration

CREATE TABLE IF NOT EXISTS community_posts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  rutina_id INT NULL,
  title VARCHAR(255) DEFAULT NULL,
  summary TEXT,
  image VARCHAR(255) DEFAULT NULL,
  is_recommendation TINYINT(1) DEFAULT 0,
  approved TINYINT(1) DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES usuario(id) ON DELETE CASCADE,
  FOREIGN KEY (rutina_id) REFERENCES rutina(id_rutina) ON DELETE SET NULL,
  INDEX (user_id),
  INDEX (approved)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE rutina MODIFY COLUMN tipo ENUM('estudio','ejercicio','compartida') NOT NULL;
select * from usuario;