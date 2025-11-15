-- Tablas mínimas para panel admin
CREATE TABLE IF NOT EXISTS `admin` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `email` VARCHAR(255) NOT NULL UNIQUE,
  `password` VARCHAR(255) NOT NULL,
  `name` VARCHAR(255),
  `avatar` VARCHAR(255),
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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

CREATE TABLE IF NOT EXISTS `user_notifications` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT DEFAULT NULL,
  `title` VARCHAR(255),
  `message` TEXT,
  `fecha_programada` DATETIME,
  `is_read` TINYINT(1) DEFAULT 0,
  `is_delivered` TINYINT(1) DEFAULT 0,
  `fecha_envio` DATETIME NULL,
  `tipo` VARCHAR(50) DEFAULT 'recordatorio',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX (`user_id`),
  INDEX (`is_read`),
  INDEX (`fecha_programada`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
