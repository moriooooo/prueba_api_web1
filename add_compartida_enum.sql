-- Migration: add 'compartida' to rutina.tipo enum
-- Execute this once against your database (use mysql client or admin tool).

ALTER TABLE rutina MODIFY COLUMN tipo ENUM('estudio','ejercicio','compartida') NOT NULL;

-- NOTE: If your MySQL version or SQL mode doesn't allow modifying enum like this when values exist,
-- you can instead create a new column, copy values, drop the old column and rename.
-- Example safer multi-step approach:
-- ALTER TABLE rutina ADD COLUMN tipo_new ENUM('estudio','ejercicio','compartida') NOT NULL DEFAULT 'estudio';
-- UPDATE rutina SET tipo_new = tipo;
-- ALTER TABLE rutina DROP COLUMN tipo;
-- ALTER TABLE rutina CHANGE COLUMN tipo_new tipo ENUM('estudio','ejercicio','compartida') NOT NULL;
