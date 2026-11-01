CREATE TYPE vehicle_class AS ENUM (
    'two_wheeler', 'car_jeep_van', 'lcv', 'bus_truck',
    'hcv_mav', 'oversized', 'exempt_other', 'unknown'
);

CREATE TYPE tolling_type AS ENUM ('open', 'closed');

CREATE TYPE identification_method AS ENUM (
    'anpr_only', 'rfid_only', 'hybrid_agreed',
    'hybrid_rfid_primary', 'hybrid_anpr_primary', 'manual', 'unresolved'
);

CREATE TYPE payment_status AS ENUM ('paid', 'pending', 'failed', 'waived', 'disputed');

CREATE TYPE trip_status AS ENUM ('in_progress', 'completed', 'abandoned');

CREATE TYPE exception_type AS ENUM (
    'low_confidence_plate', 'tag_mismatch', 'no_identification',
    'tag_not_found', 'policy_violation', 'device_fault'
);

CREATE TYPE device_type AS ENUM ('camera_front', 'camera_rear', 'rfid_reader', 'barrier');

CREATE TYPE device_status AS ENUM ('online', 'degraded', 'offline');

CREATE TYPE user_role AS ENUM ('admin', 'operator', 'auditor', 'viewer');