from sqlalchemy import Column, Date, Float, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
import csv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
# pool_pre_ping validates a pooled connection before use, so a DB restart or
# an idle-timeout drop surfaces as a transparent reconnect instead of an error
# on the next request.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def _resolve_delay_cases_csv_path() -> str:
    """
    Resolve one canonical delay-cases CSV path for runtime use.

    Priority:
    1) DELAY_CASES_CSV_PATH env var (if set and exists)
    2) performance/data/delay_data.csv
    3) research/datasets/delay-cases/delay_data.csv
    """
    configured = os.getenv("DELAY_CASES_CSV_PATH")
    if configured:
        configured_abs = os.path.abspath(configured)
        if os.path.exists(configured_abs):
            return configured_abs
        raise FileNotFoundError(
            f"DELAY_CASES_CSV_PATH is set but file not found: {configured_abs}"
        )

    canonical_local = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "data", "delay_data.csv")
    )
    if os.path.exists(canonical_local):
        return canonical_local

    research_fallback = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "research",
            "datasets",
            "delay-cases",
            "delay_data.csv",
        )
    )
    if os.path.exists(research_fallback):
        return research_fallback

    raise FileNotFoundError(
        "delay_data.csv not found. Checked: "
        f"{canonical_local} and {research_fallback}"
    )


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    district = Column(String(100), nullable=False)
    province = Column(String(100), nullable=False)
    floors = Column(Integer, nullable=False)
    building_type = Column(String(100))
    start_date = Column(Date)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)


class Phase(Base):
    __tablename__ = "phases"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False)
    phase_group = Column(String(100), nullable=False)
    sub_phase = Column(String(100), nullable=False)
    planned_start = Column(Date)
    planned_end = Column(Date)
    planned_duration_days = Column(Integer)
    sequence = Column(Integer, nullable=False)


class ProgressUpdate(Base):
    __tablename__ = "progress_updates"
    id = Column(Integer, primary_key=True, index=True)
    phase_id = Column(Integer, nullable=False)
    planned_percent = Column(Float)
    actual_percent = Column(Float)
    actual_days_used = Column(Integer)
    labour_availability = Column(Float)
    material_supply = Column(Integer)
    weather_severity = Column(Float)
    entered_by = Column(String(100))


class DelayAssessment(Base):
    __tablename__ = "delay_assessments"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False)
    phase_id = Column(Integer, nullable=False)
    spi_id = Column(Integer, nullable=False)
    progress_update_id = Column(Integer, nullable=False)
    delay_category = Column(String(100), nullable=False)
    labour_availability_label = Column(String(50), nullable=False)
    labour_availability_score = Column(Float, nullable=False)
    material_supply_label = Column(String(10), nullable=False)
    material_supply_score = Column(Integer, nullable=False)
    weather_severity_label = Column(String(50), nullable=False)
    weather_severity_score = Column(Float, nullable=False)


def get_db_session():
    return SessionLocal()



def _column_exists(conn, table_name: str, column_name: str) -> bool:
    row = conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = :table_name
              AND column_name = :column_name
            LIMIT 1
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).fetchone()
    return row is not None


def _constraint_exists(conn, table_name: str, constraint_name: str) -> bool:
    row = conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.table_constraints
            WHERE table_name = :table_name
              AND constraint_name = :constraint_name
            LIMIT 1
            """
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    ).fetchone()
    return row is not None


def _index_exists(conn, index_name: str) -> bool:
    row = conn.execute(
        text(
            """
            SELECT 1
            FROM pg_indexes
            WHERE indexname = :index_name
            LIMIT 1
            """
        ),
        {"index_name": index_name},
    ).fetchone()
    return row is not None


def _create_projects_table(conn):
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                district VARCHAR(100) NOT NULL,
                province VARCHAR(100) NOT NULL,
                floors INTEGER NOT NULL,
                building_type VARCHAR(100),
                start_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    if not _column_exists(conn, "projects", "province"):
        conn.execute(text("ALTER TABLE projects ADD COLUMN province VARCHAR(100)"))

    # Site coordinates (map-based location picker). Nullable - existing
    # projects created before this feature simply have NULL here and keep
    # working via the district-name weather fallback (see
    # weather/weather_client.py). No NOT NULL guard needed since there is
    # no constraint to enforce.
    if not _column_exists(conn, "projects", "latitude"):
        conn.execute(text("ALTER TABLE projects ADD COLUMN latitude FLOAT"))
    if not _column_exists(conn, "projects", "longitude"):
        conn.execute(text("ALTER TABLE projects ADD COLUMN longitude FLOAT"))

    # Guarded migration: only enforce NOT NULL if it can actually apply. An
    # unconditional ALTER TABLE here would hard-crash app startup for the
    # entire application if any existing row has a NULL province - not just
    # for the affected project. Skips gracefully instead, logs a warning,
    # and leaves those specific rows exactly as they are; the constraint
    # will apply automatically on a future startup once the data is clean.
    null_count = conn.execute(
        text("SELECT COUNT(*) FROM projects WHERE province IS NULL")
    ).scalar()
    if null_count:
        print(
            f"[performance] WARNING: {null_count} project(s) have NULL province; "
            "skipping NOT NULL enforcement on 'projects.province' until resolved. "
            "Predictions for those specific project(s) will fail validation "
            "until province is set - see pipeline/feature_engineer.py."
        )
    else:
        conn.execute(text("ALTER TABLE projects ALTER COLUMN province SET NOT NULL"))


def _create_phases_table(conn):
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS phases (
                id SERIAL PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                phase_group VARCHAR(100),
                phase_name VARCHAR(100),
                planned_start DATE,
                planned_end DATE,
                planned_duration_days INTEGER
            )
            """
        )
    )
    if not _column_exists(conn, "phases", "sub_phase"):
        conn.execute(text("ALTER TABLE phases ADD COLUMN sub_phase VARCHAR(100)"))
    if not _column_exists(conn, "phases", "sequence"):
        conn.execute(text("ALTER TABLE phases ADD COLUMN sequence INTEGER"))
    if not _column_exists(conn, "phases", "phase_group"):
        conn.execute(text("ALTER TABLE phases ADD COLUMN phase_group VARCHAR(100)"))


def _migrate_phases_schema(conn):
    conn.execute(
        text(
            """
            UPDATE phases
               SET sub_phase = phase_name
             WHERE sub_phase IS NULL
               AND phase_name IS NOT NULL
            """
        )
    )

    conn.execute(
        text(
            """
            WITH ordered AS (
              SELECT id,
                     ROW_NUMBER() OVER (
                       PARTITION BY project_id
                       ORDER BY planned_start NULLS LAST, id
                     ) AS seq
              FROM phases
            )
            UPDATE phases p
               SET sequence = o.seq
              FROM ordered o
             WHERE p.id = o.id
               AND p.sequence IS NULL
            """
        )
    )

    conn.execute(
        text(
            """
            UPDATE phases
               SET phase_group = 'Unknown'
             WHERE phase_group IS NULL OR trim(phase_group) = ''
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE phases
               SET sub_phase = 'Unknown'
             WHERE sub_phase IS NULL OR trim(sub_phase) = ''
            """
        )
    )

    conn.execute(text("ALTER TABLE phases ALTER COLUMN phase_group SET NOT NULL"))
    conn.execute(text("ALTER TABLE phases ALTER COLUMN sub_phase SET NOT NULL"))
    conn.execute(text("ALTER TABLE phases ALTER COLUMN sequence SET NOT NULL"))

    if not _constraint_exists(conn, "phases", "uq_phases_project_sequence"):
        conn.execute(
            text(
                """
                ALTER TABLE phases
                ADD CONSTRAINT uq_phases_project_sequence
                UNIQUE (project_id, sequence)
                """
            )
        )


def _create_progress_updates_table(conn):
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS progress_updates (
                id SERIAL PRIMARY KEY,
                phase_id INTEGER REFERENCES phases(id),
                update_date DATE DEFAULT CURRENT_DATE,
                planned_percent FLOAT,
                actual_percent FLOAT,
                actual_days_used INTEGER,
                labour_availability FLOAT,
                material_supply INTEGER,
                weather_severity FLOAT,
                entered_by VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def _migrate_progress_updates_schema(conn):
    old_col = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'progress_updates'
              AND column_name = 'material_supply_status'
            """
        )
    ).fetchone()
    if old_col:
        conn.execute(
            text(
                """
                ALTER TABLE progress_updates
                RENAME COLUMN material_supply_status TO material_supply
                """
            )
        )


def _create_spi_results_table(conn):
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS spi_results (
                id SERIAL PRIMARY KEY,
                phase_id INTEGER REFERENCES phases(id),
                update_id INTEGER REFERENCES progress_updates(id),
                spi_value FLOAT NOT NULL,
                alert_level VARCHAR(20) NOT NULL,
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def _create_delay_assessments_table(conn):
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS delay_assessments (
                id SERIAL PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                phase_id INTEGER REFERENCES phases(id),
                spi_id INTEGER REFERENCES spi_results(id),
                progress_update_id INTEGER REFERENCES progress_updates(id),
                delay_category VARCHAR(100) NOT NULL,
                labour_availability_label VARCHAR(50) NOT NULL,
                labour_availability_score FLOAT NOT NULL,
                material_supply_label VARCHAR(10) NOT NULL,
                material_supply_score INTEGER NOT NULL,
                weather_severity_label VARCHAR(50) NOT NULL,
                weather_severity_score FLOAT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def _create_predictions_table(conn):
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id SERIAL PRIMARY KEY,
                phase_id INTEGER REFERENCES phases(id),
                spi_id INTEGER REFERENCES spi_results(id),
                delay_risk VARCHAR(20) NOT NULL,
                estimated_delay_days FLOAT,
                predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def _migrate_predictions_schema(conn):
    if not _column_exists(conn, "predictions", "assessment_id"):
        conn.execute(
            text(
                """
                ALTER TABLE predictions
                ADD COLUMN assessment_id INTEGER REFERENCES delay_assessments(id)
                """
            )
        )
    if not _column_exists(conn, "predictions", "cumulative_delay_days"):
        conn.execute(
            text(
                """
                ALTER TABLE predictions
                ADD COLUMN cumulative_delay_days INTEGER
                """
            )
        )


def _create_alerts_table(conn):
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id SERIAL PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                phase_id INTEGER REFERENCES phases(id),
                alert_type VARCHAR(20) NOT NULL,
                message TEXT,
                is_resolved BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def _migrate_alerts_schema(conn):
    if not _column_exists(conn, "alerts", "spi_id"):
        conn.execute(
            text(
                """
                ALTER TABLE alerts
                ADD COLUMN spi_id INTEGER REFERENCES spi_results(id)
                """
            )
        )


def _create_recommendations_table(conn):
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS recommendations (
                id SERIAL PRIMARY KEY,
                prediction_id INTEGER REFERENCES predictions(id),
                explanation TEXT,
                recommendations TEXT,
                similar_cases_used TEXT,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def _create_delay_cases_table(conn):
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS delay_cases (
                id SERIAL PRIMARY KEY,
                phase_group VARCHAR(100),
                sub_phase VARCHAR(100),
                district VARCHAR(100),
                province VARCHAR(100),
                floors INTEGER,
                delay_category TEXT,
                labour_availability FLOAT,
                material_supply INTEGER,
                weather_severity FLOAT,
                cumulative_delay INTEGER,
                delay_risk VARCHAR(20),
                delay_days INTEGER,
                cause_of_delay TEXT,
                corrective_action_taken TEXT,
                construction_status TEXT
            )
            """
        )
    )
    if not _column_exists(conn, "delay_cases", "phase_group"):
        conn.execute(text("ALTER TABLE delay_cases ADD COLUMN phase_group VARCHAR(100)"))
    if not _column_exists(conn, "delay_cases", "sub_phase"):
        conn.execute(text("ALTER TABLE delay_cases ADD COLUMN sub_phase VARCHAR(100)"))


def _create_indexes(conn):
    index_statements = {
        "idx_phases_project_sequence": """
            CREATE INDEX idx_phases_project_sequence
            ON phases (project_id, sequence)
        """,
        "idx_progress_phase_created": """
            CREATE INDEX idx_progress_phase_created
            ON progress_updates (phase_id, created_at DESC)
        """,
        "idx_spi_phase_time": """
            CREATE INDEX idx_spi_phase_time
            ON spi_results (phase_id, calculated_at DESC)
        """,
        "idx_alerts_project_active": """
            CREATE INDEX idx_alerts_project_active
            ON alerts (project_id, is_resolved, created_at DESC)
        """,
        "idx_predictions_phase_time": """
            CREATE INDEX idx_predictions_phase_time
            ON predictions (phase_id, predicted_at DESC)
        """,
        "idx_recommendations_prediction_time": """
            CREATE INDEX idx_recommendations_prediction_time
            ON recommendations (prediction_id, generated_at DESC)
        """,
        "idx_assessments_spi": """
            CREATE INDEX idx_assessments_spi
            ON delay_assessments (spi_id)
        """,
        "idx_assessments_phase_time": """
            CREATE INDEX idx_assessments_phase_time
            ON delay_assessments (phase_id, created_at DESC)
        """,
    }
    for index_name, stmt in index_statements.items():
        if not _index_exists(conn, index_name):
            conn.execute(text(stmt))


def _seed_delay_cases_if_empty(conn):
    row = conn.execute(text("SELECT COUNT(*) FROM delay_cases")).fetchone()
    count = row[0] if row else 0
    if count > 0:
        return

    csv_path = _resolve_delay_cases_csv_path()

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            conn.execute(
                text(
                    """
                    INSERT INTO delay_cases (
                        phase_group, sub_phase, district, province, floors,
                        delay_category, labour_availability, material_supply,
                        weather_severity, cumulative_delay, delay_risk, delay_days,
                        cause_of_delay, corrective_action_taken, construction_status
                    ) VALUES (
                        :phase_group, :sub_phase, :district, :province, :floors,
                        :delay_category, :labour_availability, :material_supply,
                        :weather_severity, :cumulative_delay, :delay_risk, :delay_days,
                        :cause_of_delay, :corrective_action_taken, :construction_status
                    )
                    """
                ),
                {
                    "phase_group": row.get("phase_group"),
                    "sub_phase": row.get("sub_phase"),
                    "district": row.get("district"),
                    "province": row.get("province"),
                    "floors": int(row["floors"]) if row.get("floors") else None,
                    "delay_category": row.get("delay_category"),
                    "labour_availability": float(row["labour_availability"])
                    if row.get("labour_availability")
                    else None,
                    "material_supply": int(row["material_supply"])
                    if row.get("material_supply")
                    else None,
                    "weather_severity": float(row["weather_severity"])
                    if row.get("weather_severity")
                    else None,
                    "cumulative_delay": int(row["cumulative_delay"])
                    if row.get("cumulative_delay")
                    else None,
                    "delay_risk": row.get("delay_risk"),
                    "delay_days": int(row["delay_days"]) if row.get("delay_days") else None,
                    "cause_of_delay": row.get("cause_of_delay"),
                    "corrective_action_taken": row.get("corrective_action_taken"),
                    "construction_status": row.get("construction_status"),
                },
            )


def _run_sanity_checks(conn):
    null_count = conn.execute(
        text(
            """
            SELECT COUNT(*) FROM phases
            WHERE sub_phase IS NULL OR sequence IS NULL
            """
        )
    ).scalar()
    dup_count = conn.execute(
        text(
            """
            SELECT COUNT(*) FROM (
              SELECT project_id, sequence, COUNT(*) c
              FROM phases
              GROUP BY project_id, sequence
              HAVING COUNT(*) > 1
            ) q
            """
        )
    ).scalar()
    if null_count:
        print(f"[WARN] phases with NULL sub_phase/sequence: {null_count}")
    if dup_count:
        print(f"[WARN] duplicate (project_id, sequence) pairs: {dup_count}")


def init_db():
    with engine.connect() as conn:
        _create_projects_table(conn)
        _create_phases_table(conn)
        _migrate_phases_schema(conn)
        _create_progress_updates_table(conn)
        _migrate_progress_updates_schema(conn)
        _create_spi_results_table(conn)
        _create_delay_assessments_table(conn)
        _create_predictions_table(conn)
        _migrate_predictions_schema(conn)
        _create_alerts_table(conn)
        _migrate_alerts_schema(conn)
        _create_recommendations_table(conn)
        _create_delay_cases_table(conn)
        _create_indexes(conn)
        _seed_delay_cases_if_empty(conn)
        _run_sanity_checks(conn)
        conn.commit()

    print("[OK] Database initialized successfully")
