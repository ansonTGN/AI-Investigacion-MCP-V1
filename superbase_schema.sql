-- Sentencia para crear la tabla 'ai_trend_reports' si no existe.
-- Esta tabla almacenará los resultados de cada ejecución de la investigación.
CREATE TABLE IF NOT EXISTS ai_trend_reports (
    id BIGSERIAL PRIMARY KEY,  -- Un identificador numérico único para cada informe, que se autoincrementa.
    date DATE NOT NULL,        -- La fecha en que se realizó la investigación.
    summary JSONB,             -- Un campo para almacenar el resumen de la investigación en formato JSONB (JSON binario, más eficiente).
    detailed_results JSONB,    -- Un campo para almacenar todos los resultados detallados.
    new_keywords JSONB,        -- Un campo para almacenar la lista de nuevas palabras clave encontradas.
    recommendations JSONB,     -- Un campo para almacenar las recomendaciones generadas.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), -- Marca de tiempo de cuándo se creó el registro. Se establece automáticamente.
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()  -- Marca de tiempo de la última actualización. Se actualizará con un trigger.
);

-- Crea un índice en la columna 'date' para que las búsquedas por fecha sean más rápidas.
CREATE INDEX IF NOT EXISTS idx_ai_trend_reports_date ON ai_trend_reports(date);

-- Crea un índice en la columna 'created_at' para optimizar las consultas ordenadas por tiempo.
CREATE INDEX IF NOT EXISTS idx_ai_trend_reports_created_at ON ai_trend_reports(created_at);

-- MEJORA SUGERIDA: Añade índices GIN a las columnas JSONB si planeas realizar consultas complejas
-- dentro de los objetos JSON. Esto puede mejorar significativamente el rendimiento de dichas consultas.
-- Descomenta las siguientes líneas si necesitas esta funcionalidad.
-- CREATE INDEX IF NOT EXISTS idx_gin_ai_trend_reports_summary ON ai_trend_reports USING GIN (summary);
-- CREATE INDEX IF NOT EXISTS idx_gin_ai_trend_reports_detailed_results ON ai_trend_reports USING GIN (detailed_results);


-- Habilita la Seguridad a Nivel de Fila (RLS) en la tabla.
-- Esto significa que, por defecto, nadie puede acceder a los datos a menos que una política lo permita explícitamente.
ALTER TABLE ai_trend_reports ENABLE ROW LEVEL SECURITY;

-- Crea una política de seguridad que permite a los usuarios autenticados leer todos los informes.
-- Es más seguro comprobar el rol explícitamente que usar `auth.uid() is not null`.
CREATE POLICY "Allow authenticated users to read reports" ON ai_trend_reports
    FOR SELECT USING (auth.role() = 'authenticated');

-- Crea una política que permite a los usuarios autenticados insertar nuevos informes.
CREATE POLICY "Allow authenticated users to insert reports" ON ai_trend_reports
    FOR INSERT WITH CHECK (auth.role() = 'authenticated');

-- Crea una política que permite a los usuarios autenticados actualizar los informes existentes.
CREATE POLICY "Allow authenticated users to update reports" ON ai_trend_reports
    FOR UPDATE USING (auth.role() = 'authenticated');

-- Crea una política que permite a los usuarios autenticados eliminar informes.
-- Es importante tener una política de DELETE si se necesita, de lo contrario será denegado por defecto.
CREATE POLICY "Allow authenticated users to delete reports" ON ai_trend_reports
    FOR DELETE USING (auth.role() = 'authenticated');


-- Crea una función de PostgreSQL. Esta función se ejecutará automáticamente
-- para actualizar la columna 'updated_at' cada vez que se modifique una fila.
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW(); -- Establece el valor de 'updated_at' a la hora actual.
    RETURN NEW;             -- Devuelve la fila modificada para que la operación continúe.
END;
$$ language 'plpgsql';

-- Elimina el trigger existente si existe para evitar errores en la re-ejecución.
DROP TRIGGER IF EXISTS update_ai_trend_reports_updated_at ON ai_trend_reports;

-- Crea un 'trigger' (disparador) que llama a la función anterior
-- antes de que se realice cualquier operación de UPDATE en la tabla.
CREATE TRIGGER update_ai_trend_reports_updated_at 
    BEFORE UPDATE ON ai_trend_reports 
    FOR EACH ROW 
    EXECUTE FUNCTION public.update_updated_at_column();

-- Opcional: Crea una 'vista' (una especie de tabla virtual) para consultar fácilmente los informes más recientes.
CREATE OR REPLACE VIEW recent_ai_trend_reports AS
SELECT *
FROM ai_trend_reports
ORDER BY created_at DESC;

-- Opcional: Crea una función de base de datos para obtener informes dentro de un rango de fechas.
CREATE OR REPLACE FUNCTION get_reports_by_date_range(
    start_date DATE,
    end_date DATE
)
-- Define la estructura de la tabla que devolverá la función.
RETURNS TABLE (
    id BIGINT,
    report_date DATE,
    summary_data JSONB,
    results_data JSONB,
    keywords_data JSONB,
    recommendations_data JSONB,
    created_timestamp TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    -- Devuelve el resultado de la consulta SELECT.
    RETURN QUERY
    SELECT 
        r.id, r.date, r.summary, r.detailed_results, r.new_keywords, r.recommendations, r.created_at
    FROM ai_trend_reports r
    WHERE r.date BETWEEN start_date AND end_date -- Filtra por el rango de fechas.
    ORDER BY r.date DESC;
END;
$$ LANGUAGE plpgsql;
