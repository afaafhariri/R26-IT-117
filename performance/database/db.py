from sqlalchemy import create_engine, text, Column, Integer, String, Float, Boolean, Date, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os
import csv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ---------------------------------------------------------------------------
# ORM Models (used by main.py route handlers)
# ---------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    district = Column(String(100), nullable=False)
    province = Column(String(100))
    floors = Column(Integer, nullable=False)
    building_type = Column(String(100))
    start_date = Column(Date)


class Phase(Base):
    __tablename__ = "phases"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer)
    phase_group = Column(String(100))
    phase_name = Column(String(100), nullable=False)
    planned_start = Column(Date)
    planned_end = Column(Date)
    planned_duration_days = Column(Integer)


class ProgressUpdate(Base):
    __tablename__ = "progress_updates"
    id = Column(Integer, primary_key=True, index=True)
    phase_id = Column(Integer)
    planned_percent = Column(Float)
    actual_percent = Column(Float)
    actual_days_used = Column(Integer)
    labour_availability = Column(Float)
    material_supply = Column(Integer)
    weather_severity = Column(Float)
    entered_by = Column(String(100))


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def get_db_session():
    return SessionLocal()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------

def init_db():
    with engine.connect() as conn:

        # ── 1. Create all 8 tables ──────────────────────────────────────────

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                district VARCHAR(100) NOT NULL,
                province VARCHAR(100),
                floors INTEGER NOT NULL,
                building_type VARCHAR(100),
                start_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # migrate: add province to existing projects table if missing
        conn.execute(text("""
            ALTER TABLE projects ADD COLUMN IF NOT EXISTS province VARCHAR(100)
        """))

        # migrate: rename material_supply_status -> material_supply if old name exists
        old_col = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'progress_updates'
              AND column_name = 'material_supply_status'
        """)).fetchone()
        if old_col:
            conn.execute(text("""
                ALTER TABLE progress_updates
                RENAME COLUMN material_supply_status TO material_supply
            """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS phases (
                id SERIAL PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                phase_group VARCHAR(100),
                phase_name VARCHAR(100) NOT NULL,
                planned_start DATE,
                planned_end DATE,
                planned_duration_days INTEGER
            )
        """))

        # migrate: add phase_group to existing phases table if missing
        conn.execute(text("""
            ALTER TABLE phases ADD COLUMN IF NOT EXISTS phase_group VARCHAR(100)
        """))

        conn.execute(text("""
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
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS spi_results (
                id SERIAL PRIMARY KEY,
                phase_id INTEGER REFERENCES phases(id),
                update_id INTEGER REFERENCES progress_updates(id),
                spi_value FLOAT NOT NULL,
                alert_level VARCHAR(20) NOT NULL,
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS predictions (
                id SERIAL PRIMARY KEY,
                phase_id INTEGER REFERENCES phases(id),
                spi_id INTEGER REFERENCES spi_results(id),
                delay_risk VARCHAR(20) NOT NULL,
                estimated_delay_days FLOAT,
                predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # ── delay_cases: migrate from old schema if needed ─────────────────
        # Check if the table exists with the NEW schema (phase_group column).
        # If not (old schema or missing), drop and recreate with new schema.
        col_check = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'delay_cases'
              AND column_name = 'phase_group'
        """)).fetchone()

        if col_check is None:
            print("[INFO] delay_cases schema outdated or missing — rebuilding...")
            conn.execute(text("DROP TABLE IF EXISTS delay_cases"))

        conn.execute(text("""
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
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alerts (
                id SERIAL PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                phase_id INTEGER REFERENCES phases(id),
                alert_type VARCHAR(20) NOT NULL,
                message TEXT,
                is_resolved BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS recommendations (
                id SERIAL PRIMARY KEY,
                prediction_id INTEGER REFERENCES predictions(id),
                explanation TEXT,
                recommendations TEXT,
                similar_cases_used TEXT,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.commit()
        print("[OK] 8 tables created")

        # ── 2. Seed delay_cases from CSV only if table is empty ─────────────

        row = conn.execute(text("SELECT COUNT(*) FROM delay_cases")).fetchone()
        count = row[0]

        if count == 0:
            csv_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "research", "datasets", "delay-cases", "delay_data.csv")
            )

            # fallback: also check local data/ copy (used inside Docker)
            local_csv = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "data", "delay_data.csv")
            )
            if not os.path.exists(csv_path) and os.path.exists(local_csv):
                csv_path = local_csv
            if not os.path.exists(csv_path):
                raise FileNotFoundError(
                    f"[ERROR] delay_data.csv not found at: {csv_path} or {local_csv}"
                )

            inserted = 0
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    conn.execute(text("""
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
                    """), {
                        "phase_group":             row.get("phase_group"),
                        "sub_phase":               row.get("sub_phase"),
                        "district":                row.get("district"),
                        "province":                row.get("province"),
                        "floors":                  int(row["floors"]) if row.get("floors") else None,
                        "delay_category":          row.get("delay_category"),
                        "labour_availability":     float(row["labour_availability"]) if row.get("labour_availability") else None,
                        "material_supply":         int(row["material_supply"]) if row.get("material_supply") else None,
                        "weather_severity":        float(row["weather_severity"]) if row.get("weather_severity") else None,
                        "cumulative_delay":        int(row["cumulative_delay"]) if row.get("cumulative_delay") else None,
                        "delay_risk":              row.get("delay_risk"),
                        "delay_days":              int(row["delay_days"]) if row.get("delay_days") else None,
                        "cause_of_delay":          row.get("cause_of_delay"),
                        "corrective_action_taken": row.get("corrective_action_taken"),
                        "construction_status":     row.get("construction_status"),
                    })
                    inserted += 1

            conn.commit()
            print(f"[OK] Delay cases seeded ({inserted} records from delay_data.csv)")
        else:
            print(f"[INFO] delay_cases already has {count} records - skipping seed")

    print("[OK] Database initialized successfully")
