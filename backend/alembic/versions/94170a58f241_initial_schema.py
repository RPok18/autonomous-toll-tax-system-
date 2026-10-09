"""initial schema

Revision ID: 94170a58f241
Revises: 
Create Date: 2026-10-10 00:46:37.805759

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '94170a58f241'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('audit_logs',
    sa.Column('audit_log_id', sa.UUID(), nullable=False),
    sa.Column('actor', sa.String(length=80), nullable=True),
    sa.Column('action', sa.String(length=100), nullable=True),
    sa.Column('resource_type', sa.String(length=50), nullable=True),
    sa.Column('resource_id', sa.String(length=100), nullable=True),
    sa.Column('metadata_json', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('audit_log_id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_actor'), 'audit_logs', ['actor'], unique=False)
    op.create_table('highways',
    sa.Column('highway_id', sa.UUID(), nullable=False),
    sa.Column('nh_number', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('states', postgresql.ARRAY(sa.String(length=2)), nullable=False),
    sa.Column('total_length_km', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('tolling_type', sa.Enum('open', 'closed', name='tolling_type', create_type=False), nullable=False),
    sa.Column('operator_name', sa.String(length=150), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('highway_id'),
    sa.UniqueConstraint('nh_number')
    )
    op.create_table('users',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('username', sa.String(length=80), nullable=False),
    sa.Column('hashed_password', sa.String(length=200), nullable=False),
    sa.Column('role', sa.Enum('admin', 'operator', 'auditor', 'viewer', name='user_role', create_type=False), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('user_id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('vehicles',
    sa.Column('vehicle_id', sa.UUID(), nullable=False),
    sa.Column('plate_number', sa.String(length=15), nullable=True),
    sa.Column('registration_state', sa.String(length=2), nullable=True),
    sa.Column('vehicle_class', sa.Enum('two_wheeler', 'car_jeep_van', 'lcv', 'bus_truck', 'hcv_mav', 'oversized', 'exempt_other', 'unknown', name='vehicle_class', create_type=False), nullable=False),
    sa.Column('fastag_id', sa.String(length=32), nullable=True),
    sa.Column('fastag_issuer_bank', sa.String(length=64), nullable=True),
    sa.Column('is_commercial', sa.Boolean(), nullable=False),
    sa.Column('is_exempt', sa.Boolean(), nullable=False),
    sa.Column('is_blacklisted', sa.Boolean(), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('vehicle_id'),
    sa.UniqueConstraint('fastag_id'),
    sa.UniqueConstraint('plate_number')
    )
    op.create_table('plazas',
    sa.Column('plaza_id', sa.UUID(), nullable=False),
    sa.Column('highway_id', sa.UUID(), nullable=False),
    sa.Column('plaza_code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('chainage_km', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('state_code', sa.String(length=2), nullable=False),
    sa.Column('latitude', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('longitude', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('num_lanes', sa.SmallInteger(), nullable=False),
    sa.Column('direction', sa.String(length=20), nullable=True),
    sa.Column('operator_name', sa.String(length=150), nullable=True),
    sa.Column('commissioned_on', sa.Date(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['highway_id'], ['highways.highway_id'], ),
    sa.PrimaryKeyConstraint('plaza_id'),
    sa.UniqueConstraint('plaza_code')
    )
    op.create_table('devices',
    sa.Column('device_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=True),
    sa.Column('device_type', sa.Enum('camera_front', 'camera_rear', 'rfid_reader', 'barrier', name='device_type', create_type=False), nullable=False),
    sa.Column('plaza_id', sa.UUID(), nullable=True),
    sa.Column('lane_id', sa.String(length=20), nullable=True),
    sa.Column('status', sa.Enum('online', 'degraded', 'offline', name='device_status', create_type=False), nullable=False),
    sa.Column('error_count_24h', sa.Integer(), nullable=True),
    sa.Column('avg_latency_ms', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['plaza_id'], ['plazas.plaza_id'], ),
    sa.PrimaryKeyConstraint('device_id')
    )
    op.create_table('segments',
    sa.Column('segment_id', sa.UUID(), nullable=False),
    sa.Column('highway_id', sa.UUID(), nullable=False),
    sa.Column('entry_plaza_id', sa.UUID(), nullable=False),
    sa.Column('exit_plaza_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=True),
    sa.Column('distance_km', sa.Numeric(precision=8, scale=2), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('entry_plaza_id <> exit_plaza_id', name='ck_segments_distinct_plazas'),
    sa.ForeignKeyConstraint(['entry_plaza_id'], ['plazas.plaza_id'], ),
    sa.ForeignKeyConstraint(['exit_plaza_id'], ['plazas.plaza_id'], ),
    sa.ForeignKeyConstraint(['highway_id'], ['highways.highway_id'], ),
    sa.PrimaryKeyConstraint('segment_id'),
    sa.UniqueConstraint('entry_plaza_id', 'exit_plaza_id', name='uq_segments_entry_exit')
    )
    op.create_table('tariffs',
    sa.Column('tariff_id', sa.UUID(), nullable=False),
    sa.Column('plaza_id', sa.UUID(), nullable=True),
    sa.Column('segment_id', sa.UUID(), nullable=True),
    sa.Column('vehicle_class', sa.Enum('two_wheeler', 'car_jeep_van', 'lcv', 'bus_truck', 'hcv_mav', 'oversized', 'exempt_other', 'unknown', name='vehicle_class', create_type=False), nullable=False),
    sa.Column('base_fare', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('rate_per_km', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('return_trip_discount_percent', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('return_trip_window_hours', sa.SmallInteger(), nullable=False),
    sa.Column('monthly_pass_fare', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('local_resident_discount_percent', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('night_surcharge_percent', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('notified_by', sa.String(length=150), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('(plaza_id IS NOT NULL AND segment_id IS NULL) OR (plaza_id IS NULL AND segment_id IS NOT NULL)', name='ck_tariffs_one_scope'),
    sa.CheckConstraint('effective_to IS NULL OR effective_to >= effective_from', name='ck_tariffs_date_range'),
    sa.ForeignKeyConstraint(['plaza_id'], ['plazas.plaza_id'], ),
    sa.ForeignKeyConstraint(['segment_id'], ['segments.segment_id'], ),
    sa.PrimaryKeyConstraint('tariff_id')
    )
    op.create_table('trips',
    sa.Column('trip_id', sa.UUID(), nullable=False),
    sa.Column('vehicle_id', sa.UUID(), nullable=False),
    sa.Column('segment_id', sa.UUID(), nullable=True),
    sa.Column('entry_plaza_id', sa.UUID(), nullable=False),
    sa.Column('entry_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('exit_plaza_id', sa.UUID(), nullable=True),
    sa.Column('exit_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('distance_travelled_km', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('status', sa.Enum('in_progress', 'completed', 'abandoned', name='trip_status', create_type=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('exit_time IS NULL OR exit_time >= entry_time', name='ck_trips_exit_after_entry'),
    sa.ForeignKeyConstraint(['entry_plaza_id'], ['plazas.plaza_id'], ),
    sa.ForeignKeyConstraint(['exit_plaza_id'], ['plazas.plaza_id'], ),
    sa.ForeignKeyConstraint(['segment_id'], ['segments.segment_id'], ),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.vehicle_id'], ),
    sa.PrimaryKeyConstraint('trip_id')
    )
    op.create_table('transactions',
    sa.Column('transaction_id', sa.UUID(), nullable=False),
    sa.Column('plaza_id', sa.UUID(), nullable=False),
    sa.Column('lane_id', sa.String(length=20), nullable=False),
    sa.Column('trip_id', sa.UUID(), nullable=True),
    sa.Column('vehicle_id', sa.UUID(), nullable=True),
    sa.Column('tariff_id', sa.UUID(), nullable=True),
    sa.Column('plate_number', sa.String(length=15), nullable=True),
    sa.Column('plate_confidence', sa.Numeric(precision=4, scale=3), nullable=True),
    sa.Column('tag_id', sa.String(length=32), nullable=True),
    sa.Column('tag_confidence', sa.Numeric(precision=4, scale=3), nullable=True),
    sa.Column('identification_method', sa.Enum('anpr_only', 'rfid_only', 'hybrid_agreed', 'hybrid_rfid_primary', 'hybrid_anpr_primary', 'manual', 'unresolved', name='identification_method', create_type=False), nullable=False),
    sa.Column('vehicle_class', sa.Enum('two_wheeler', 'car_jeep_van', 'lcv', 'bus_truck', 'hcv_mav', 'oversized', 'exempt_other', 'unknown', name='vehicle_class', create_type=False), nullable=True),
    sa.Column('base_amount', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('discount_amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('surcharge_amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('amount_charged', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('payment_status', sa.Enum('paid', 'pending', 'failed', 'waived', 'disputed', name='payment_status', create_type=False), nullable=False),
    sa.Column('applied_rules', sa.JSON(), nullable=True),
    sa.Column('is_exception', sa.Boolean(), nullable=False),
    sa.Column('latency_ms', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('transaction_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['plaza_id'], ['plazas.plaza_id'], ),
    sa.ForeignKeyConstraint(['tariff_id'], ['tariffs.tariff_id'], ),
    sa.ForeignKeyConstraint(['trip_id'], ['trips.trip_id'], ),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.vehicle_id'], ),
    sa.PrimaryKeyConstraint('transaction_id')
    )
    op.create_table('exceptions',
    sa.Column('exception_id', sa.UUID(), nullable=False),
    sa.Column('transaction_id', sa.UUID(), nullable=True),
    sa.Column('plaza_id', sa.UUID(), nullable=True),
    sa.Column('lane_id', sa.String(length=20), nullable=True),
    sa.Column('exception_type', sa.Enum('low_confidence_plate', 'tag_mismatch', 'no_identification', 'tag_not_found', 'policy_violation', 'device_fault', name='exception_type', create_type=False), nullable=False),
    sa.Column('details', sa.Text(), nullable=True),
    sa.Column('resolved', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['plaza_id'], ['plazas.plaza_id'], ),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.transaction_id'], ),
    sa.PrimaryKeyConstraint('exception_id')
    )
    # ### end Alembic commands ###