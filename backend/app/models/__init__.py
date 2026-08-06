# Importing every model module here means "import app.models" (used by
# Alembic's env.py) is enough to register all tables on Base.metadata,
# even though nothing in this file directly uses the names.
from app.models.user import User  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.group import Group, UserGroupProject  # noqa: F401
from app.models.user_session import UserSession  # noqa: F401
from app.models.password_reset_token import PasswordResetToken  # noqa: F401
from app.models.commodity import Commodity  # noqa: F401
from app.models.analysis import Analysis  # noqa: F401
from app.models.analysis_entry import AnalysisEntry  # noqa: F401
from app.models.process_type import ProcessType  # noqa: F401
from app.models.tolerance_class import ToleranceClass  # noqa: F401
from app.models.image import Image  # noqa: F401
from app.models.marker import Marker  # noqa: F401
from app.models.chain_component import ChainComponent  # noqa: F401
