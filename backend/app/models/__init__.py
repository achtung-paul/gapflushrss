# Importing every model module here means "import app.models" (used by
# both alembic/env.py and alembic_project/env.py) is enough to register
# every table on its declarative base's metadata, even though nothing in
# this file directly uses the names. Central models (Base) and
# project-scoped models (ProjectBase) are listed together -- each
# Alembic chain only looks at its own base's metadata (see
# db/base.py vs db/project_base.py), so mixing the imports here is
# harmless and keeps this file simple.
from app.models.client import Client  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.group import Group, UserGroupProject  # noqa: F401
from app.models.user_session import UserSession  # noqa: F401
from app.models.password_reset_token import PasswordResetToken  # noqa: F401
from app.models.postgres_service import PostgresService  # noqa: F401
from app.models.minio_service import MinioService  # noqa: F401
from app.models.postgres_server import PostgresServer  # noqa: F401
from app.models.minio_server import MinioServer  # noqa: F401
from app.models.process_type import ProcessType  # noqa: F401
from app.models.tolerance_group import ToleranceGroup  # noqa: F401
from app.models.dimension_range import DimensionRange  # noqa: F401
from app.models.tolerance_value import ToleranceValue  # noqa: F401
from app.models.commodity import Commodity  # noqa: F401
from app.models.analysis import Analysis  # noqa: F401
from app.models.analysis_entry import AnalysisEntry  # noqa: F401
from app.models.image import Image  # noqa: F401
from app.models.marker import Marker  # noqa: F401
from app.models.analysis_image import AnalysisImage  # noqa: F401
from app.models.chain_component import ChainComponent  # noqa: F401
from app.models.standard_tolerance import StandardTolerance  # noqa: F401
from app.models.banner import Banner  # noqa: F401
from app.models.angled_component import AngledComponent  # noqa: F401
from app.models.statistical_model_setting import StatisticalModelSetting  # noqa: F401
from app.models.security_setting import SecuritySetting  # noqa: F401
from app.models.user_totp import UserTotp  # noqa: F401
from app.models.login_challenge import LoginChallenge  # noqa: F401
