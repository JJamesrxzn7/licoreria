-- Aplicar solo tras respaldo y pruebas con la cuenta dedicada de la API.
BEGIN;

CREATE TABLE sesiones_revocadas (
    token_hash char(64) PRIMARY KEY,
    expira_en timestamptz NOT NULL
);
ALTER TABLE sesiones_revocadas ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE sesiones_revocadas FROM PUBLIC;
CREATE POLICY sesiones_revocadas_lectura ON sesiones_revocadas
    FOR SELECT TO PUBLIC USING (true);
CREATE POLICY sesiones_revocadas_insercion ON sesiones_revocadas
    FOR INSERT TO PUBLIC WITH CHECK (true);

-- Las políticas no conceden privilegios de tabla. Un administrador debe
-- conceder SELECT e INSERT únicamente a la cuenta dedicada de la API.
COMMIT;
