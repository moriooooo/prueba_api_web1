

-- If you already have community_posts table with approved default 1, run this to change it:
-- ALTER TABLE community_posts MODIFY COLUMN approved TINYINT(1) DEFAULT 0;

-- Ensure recommendations and user_recommendations exist
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
