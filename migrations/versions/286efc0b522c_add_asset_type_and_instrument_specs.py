"""add asset_type and instrument_specs

Revision ID: 286efc0b522c
Revises: bdb4b66148e7
Create Date: 2026-10-05 12:29:12.420034

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "286efc0b522c"
down_revision: Union[str, Sequence[str], None] = "bdb4b66148e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    SQLite does not support ALTER TABLE DROP/ADD CONSTRAINT.
    We use batch_alter_table to recreate the `candles` table with the
    new column, new unique constraint, and new indexes.
    """
    # 1. New table: instrument_specs.
    op.create_table(
        "instrument_specs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("asset_type", sa.String(length=10), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("contract_multiplier", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("tick_size", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("tick_value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("expiration_date", sa.DateTime(), nullable=True),
        sa.Column("base_asset", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "asset_type", name="uq_spec_symbol_asset"),
    )
    op.create_index(
        op.f("ix_instrument_specs_symbol"),
        "instrument_specs",
        ["symbol"],
        unique=False,
    )

    # 2. Rebuild `candles` with asset_type and new constraints/indexes.
    with op.batch_alter_table("candles", schema=None) as batch_op:
        # Add asset_type. server_default='stock' fills existing rows.
        batch_op.add_column(
            sa.Column(
                "asset_type",
                sa.String(length=10),
                server_default="stock",
                nullable=False,
            )
        )
        # Drop old indexes and unique constraint.
        batch_op.drop_index("ix_candle_symbol_tf_ts")
        batch_op.drop_constraint("uq_candle_symbol_tf_ts", type_="unique")
        # Create new indexes and unique constraint.
        batch_op.create_index(
            "ix_candle_symbol_asset_tf_ts",
            ["symbol", "asset_type", "timeframe", "timestamp"],
            unique=False,
        )
        batch_op.create_index(
            "ix_candles_asset_type",
            ["asset_type"],
            unique=False,
        )
        batch_op.create_unique_constraint(
            "uq_candle_symbol_asset_tf_ts",
            ["symbol", "asset_type", "timeframe", "timestamp"],
        )


def downgrade() -> None:
    """Downgrade schema.

    Reverse: restore old indexes and unique constraint, drop asset_type.
    Also uses batch_alter_table for SQLite compatibility.
    """
    with op.batch_alter_table("candles", schema=None) as batch_op:
        batch_op.drop_constraint("uq_candle_symbol_asset_tf_ts", type_="unique")
        batch_op.drop_index("ix_candles_asset_type")
        batch_op.drop_index("ix_candle_symbol_asset_tf_ts")
        batch_op.create_unique_constraint(
            "uq_candle_symbol_tf_ts",
            ["symbol", "timeframe", "timestamp"],
        )
        batch_op.create_index(
            "ix_candle_symbol_tf_ts",
            ["symbol", "timeframe", "timestamp"],
            unique=False,
        )
        batch_op.drop_column("asset_type")

    # Drop instrument_specs.
    op.drop_index(op.f("ix_instrument_specs_symbol"), table_name="instrument_specs")
    op.drop_table("instrument_specs")
