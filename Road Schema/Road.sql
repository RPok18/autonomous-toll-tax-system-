CREATE EXTENSION IF NOT EXISTS pgcrypto;  


-- Enums


CREATE TYPE vehicle_class AS ENUM (
    'two_wheeler',      -- exempt at most plazas
    'car_jeep_van',
    'lcv',               -- light commercial vehicle
    'bus_truck',
    'hcv_mav',            -- heavy / multi-axle vehicle
    'oversized',
    'exempt_other',       -- government, defence, ambulance, etc.
    'unknown'
);

CREATE TYPE tolling_type AS ENUM ('open', 'closed');

CREATE TYPE identification_method AS ENUM (
    'anpr_only',
    'rfid_only',
    'hybrid_agreed',
    'hybrid_rfid_primary',
    'hybrid_anpr_primary',
    'manual',
    'unresolved'
);

CREATE TYPE payment_status AS ENUM ('paid', 'pending', 'failed', 'waived', 'disputed');

CREATE TYPE trip_status AS ENUM ('in_progress', 'completed', 'abandoned');

-- ---------------------------------------------------------------------------
-- highways
-- ---------------------------------------------------------------------------

CREATE TABLE highways (
    highway_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nh_number       VARCHAR(20) NOT NULL,            -- e.g. 'NH-48', 'NE-1' (expressway)
    name            VARCHAR(150) NOT NULL,           -- e.g. 'Delhi–Mumbai Expressway'
    states          TEXT[] NOT NULL,                 -- 2-letter state/UT codes traversed, e.g. '{DL,HR,RJ,MP,GJ,MH}'
    total_length_km NUMERIC(8,2),
    tolling_type    tolling_type NOT NULL DEFAULT 'open',
    operator_name   VARCHAR(150),                    -- NHAI / concessionaire (BOT/HAM/TOT)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_highways_nh_number UNIQUE (nh_number)
);

COMMENT ON COLUMN highways.states IS 'Ordered array of state/UT codes the highway passes through.';

-- ---------------------------------------------------------------------------
-- plazas
-- ---------------------------------------------------------------------------

CREATE TABLE plazas (
    plaza_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    highway_id      UUID NOT NULL REFERENCES highways(highway_id) ON DELETE RESTRICT,
    plaza_code      VARCHAR(20) NOT NULL,            -- NHAI-assigned plaza code
    name            VARCHAR(150) NOT NULL,
    chainage_km     NUMERIC(8,2),                    -- distance marker along the highway
    state_code      CHAR(2) NOT NULL,
    latitude        NUMERIC(9,6),
    longitude       NUMERIC(9,6),
    num_lanes       SMALLINT NOT NULL DEFAULT 1 CHECK (num_lanes > 0),
    direction       VARCHAR(20),                     -- e.g. 'northbound', 'both'
    operator_name   VARCHAR(150),                    -- concessionaire operating this plaza
    commissioned_on DATE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_plazas_code UNIQUE (plaza_code)
);

CREATE INDEX ix_plazas_highway_id ON plazas(highway_id);
CREATE INDEX ix_plazas_state_code ON plazas(state_code);

-- ---------------------------------------------------------------------------
-- segments
-- A segment is a billable entry↔exit pair on a closed/distance-based
-- corridor. For a purely open-tolling highway this table can be left empty.
-- ---------------------------------------------------------------------------

CREATE TABLE segments (
    segment_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    highway_id      UUID NOT NULL REFERENCES highways(highway_id) ON DELETE RESTRICT,
    entry_plaza_id  UUID NOT NULL REFERENCES plazas(plaza_id) ON DELETE RESTRICT,
    exit_plaza_id   UUID NOT NULL REFERENCES plazas(plaza_id) ON DELETE RESTRICT,
    name            VARCHAR(150),
    distance_km     NUMERIC(8,2) NOT NULL CHECK (distance_km > 0),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_segments_distinct_plazas CHECK (entry_plaza_id <> exit_plaza_id),
    CONSTRAINT uq_segments_entry_exit UNIQUE (entry_plaza_id, exit_plaza_id)
);

CREATE INDEX ix_segments_highway_id ON segments(highway_id);
CREATE INDEX ix_segments_entry_plaza ON segments(entry_plaza_id);
CREATE INDEX ix_segments_exit_plaza ON segments(exit_plaza_id);

-- ---------------------------------------------------------------------------
-- tariffs
-- A tariff applies to either a plaza (open, flat-fee tolling) OR a segment
-- (closed, distance-based tolling) — never both, never neither.
-- Multiple rows per (plaza|segment, vehicle_class) capture rate history via
-- effective_from/effective_to (effective_to NULL = currently in force).
-- ---------------------------------------------------------------------------

CREATE TABLE tariffs (
    tariff_id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plaza_id                       UUID REFERENCES plazas(plaza_id) ON DELETE CASCADE,
    segment_id                     UUID REFERENCES segments(segment_id) ON DELETE CASCADE,
    vehicle_class                  vehicle_class NOT NULL,

    base_fare                      NUMERIC(10,2) NOT NULL CHECK (base_fare >= 0),
    rate_per_km                    NUMERIC(10,2) CHECK (rate_per_km >= 0),  -- used when segment_id IS NOT NULL

    return_trip_discount_percent   NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (return_trip_discount_percent BETWEEN 0 AND 100),
    return_trip_window_hours       SMALLINT NOT NULL DEFAULT 24,
    monthly_pass_fare              NUMERIC(10,2),
    local_resident_discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (local_resident_discount_percent BETWEEN 0 AND 100),
    night_surcharge_percent        NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (night_surcharge_percent >= 0),

    currency                       CHAR(3) NOT NULL DEFAULT 'INR',
    effective_from                 DATE NOT NULL,
    effective_to                   DATE,                -- NULL = currently in force
    notified_by                    VARCHAR(150),         -- e.g. NHAI notification reference

    created_at                     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_tariffs_one_scope CHECK (
        (plaza_id IS NOT NULL AND segment_id IS NULL) OR
        (plaza_id IS NULL AND segment_id IS NOT NULL)
    ),
    CONSTRAINT ck_tariffs_date_range CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE INDEX ix_tariffs_plaza_lookup ON tariffs(plaza_id, vehicle_class, effective_from);
CREATE INDEX ix_tariffs_segment_lookup ON tariffs(segment_id, vehicle_class, effective_from);

-- Only one currently-effective tariff per (plaza|segment, vehicle_class).
CREATE UNIQUE INDEX uq_tariffs_active_plaza
    ON tariffs(plaza_id, vehicle_class)
    WHERE effective_to IS NULL AND plaza_id IS NOT NULL;

CREATE UNIQUE INDEX uq_tariffs_active_segment
    ON tariffs(segment_id, vehicle_class)
    WHERE effective_to IS NULL AND segment_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- vehicles
-- ---------------------------------------------------------------------------

CREATE TABLE vehicles (
    vehicle_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plate_number        VARCHAR(15) NOT NULL,          -- normalized, e.g. 'MH12AB1234'
    registration_state  CHAR(2),
    vehicle_class       vehicle_class NOT NULL DEFAULT 'unknown',
    fastag_id           VARCHAR(32),                    -- FASTag-like RFID tag ID
    fastag_issuer_bank  VARCHAR(64),
    is_commercial       BOOLEAN NOT NULL DEFAULT FALSE,
    is_exempt           BOOLEAN NOT NULL DEFAULT FALSE,  -- govt/defence/ambulance/etc.
    is_blacklisted      BOOLEAN NOT NULL DEFAULT FALSE,  -- fraud/non-payment hold
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_vehicles_plate_number UNIQUE (plate_number),
    CONSTRAINT uq_vehicles_fastag_id UNIQUE (fastag_id)
);

CREATE INDEX ix_vehicles_fastag_id ON vehicles(fastag_id) WHERE fastag_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- trips
-- One full journey on a closed/distance-based corridor (entry -> exit).
-- Not used for pure open-tolling highways.
-- ---------------------------------------------------------------------------

CREATE TABLE trips (
    trip_id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id              UUID NOT NULL REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT,
    segment_id              UUID REFERENCES segments(segment_id) ON DELETE SET NULL,
    entry_plaza_id          UUID NOT NULL REFERENCES plazas(plaza_id) ON DELETE RESTRICT,
    entry_time              TIMESTAMPTZ NOT NULL,
    exit_plaza_id           UUID REFERENCES plazas(plaza_id) ON DELETE RESTRICT,
    exit_time               TIMESTAMPTZ,
    distance_travelled_km   NUMERIC(8,2),
    status                  trip_status NOT NULL DEFAULT 'in_progress',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_trips_exit_after_entry CHECK (exit_time IS NULL OR exit_time >= entry_time)
);

CREATE INDEX ix_trips_vehicle_id ON trips(vehicle_id);
CREATE INDEX ix_trips_entry_plaza ON trips(entry_plaza_id, entry_time);
CREATE INDEX ix_trips_exit_plaza ON trips(exit_plaza_id, exit_time);
CREATE INDEX ix_trips_status ON trips(status) WHERE status = 'in_progress';

-- ---------------------------------------------------------------------------
-- transactions
-- One auditable toll charge event (one row per plaza pass in open tolling;
-- typically the exit-plaza event in closed tolling, linked via trip_id).
-- ---------------------------------------------------------------------------

CREATE TABLE transactions (
    transaction_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plaza_id            UUID NOT NULL REFERENCES plazas(plaza_id) ON DELETE RESTRICT,
    lane_id             VARCHAR(20) NOT NULL,
    trip_id             UUID REFERENCES trips(trip_id) ON DELETE SET NULL,
    vehicle_id          UUID REFERENCES vehicles(vehicle_id) ON DELETE SET NULL,
    tariff_id           UUID REFERENCES tariffs(tariff_id) ON DELETE SET NULL,

    -- Point-in-time capture (denormalized so history is preserved even if
    -- the vehicle record's plate/tag is later corrected/re-linked):
    plate_number            VARCHAR(15),
    plate_confidence        NUMERIC(4,3) CHECK (plate_confidence BETWEEN 0 AND 1),
    tag_id                  VARCHAR(32),
    tag_confidence           NUMERIC(4,3) CHECK (tag_confidence BETWEEN 0 AND 1),
    identification_method   identification_method NOT NULL DEFAULT 'unresolved',
    vehicle_class            vehicle_class,

    base_amount          NUMERIC(10,2),
    discount_amount      NUMERIC(10,2) NOT NULL DEFAULT 0,
    surcharge_amount     NUMERIC(10,2) NOT NULL DEFAULT 0,
    amount_charged       NUMERIC(10,2) NOT NULL DEFAULT 0,
    currency             CHAR(3) NOT NULL DEFAULT 'INR',
    payment_status       payment_status NOT NULL DEFAULT 'pending',

    applied_rules        JSONB NOT NULL DEFAULT '[]',   -- audit trail: which tariff/discount/surcharge rules fired
    is_exception         BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms           NUMERIC(8,2),                   -- end-to-end pipeline latency for this pass (P5)

    transaction_time     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_transactions_plaza_time ON transactions(plaza_id, transaction_time);
CREATE INDEX ix_transactions_vehicle_id ON transactions(vehicle_id);
CREATE INDEX ix_transactions_plate_number ON transactions(plate_number);
CREATE INDEX ix_transactions_trip_id ON transactions(trip_id);
CREATE INDEX ix_transactions_exceptions ON transactions(plaza_id, transaction_time) WHERE is_exception;
CREATE INDEX ix_transactions_applied_rules_gin ON transactions USING GIN (applied_rules);

COMMENT ON COLUMN transactions.applied_rules IS
  'Ordered list of rule identifiers that fired for this charge, e.g. ["tariff:base","discount:local_resident(-50%)"] — the audit trail required by P3.';