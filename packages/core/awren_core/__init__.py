"""Awren Core — Base entity, event, and relationship models."""
from awren_core.database import Base, create_session, get_session_local, init_db
from awren_core.interfaces import RepositoryInterface, ServiceInterface
from awren_core.models import BaseEntity, BaseEvent, BaseRelationship, EntityType, EventType, RelationshipType
from awren_core.orm_models import (
    AudioTranscriptionModel, CausalChainModel, ConversationModel, EntityModel,
    EntityVersionModel, EventModel, ImportJobModel, KnowledgeEdgeModel,
    KnowledgeNodeModel, LlmSettingsModel, MessageModel, OntologyPropertyModel,
    OntologyTypeModel, PermissionModel, RelationshipModel, RoleModel, UserModel,
)
from awren_core.repositories import EntityRepository, EventRepository, RelationshipRepository
from awren_core.services import EventService
from awren_core.settings import Settings, get_settings
from awren_core.auth import (
    create_access_token, decode_access_token, get_current_user,
    get_optional_user, hash_password, require_permission, require_role,
    seed_roles_and_permissions, verify_password,
)
from awren_core.knowledge import KnowledgeEngine
from awren_core.causality import CausalEngine
from awren_core.explainability import ExplainabilityEngine, Explanation

__all__ = [
    "BaseEntity", "BaseRelationship", "BaseEvent",
    "EntityType", "RelationshipType", "EventType",
    "RepositoryInterface", "ServiceInterface",
    "EntityRepository", "RelationshipRepository", "EventRepository",
    "EntityModel", "RelationshipModel", "EventModel",
    "UserModel", "RoleModel", "PermissionModel",
    "KnowledgeNodeModel", "KnowledgeEdgeModel", "CausalChainModel",
    "ConversationModel", "MessageModel", "EventModel",
    "LlmSettingsModel", "ImportJobModel", "AudioTranscriptionModel",
    "EntityVersionModel", "OntologyTypeModel", "OntologyPropertyModel",
    "Base", "create_session", "get_session_local", "init_db",
    "EventService",
    "Settings", "get_settings",
    "create_access_token", "decode_access_token",
    "get_current_user", "get_optional_user",
    "hash_password", "verify_password",
    "require_role", "require_permission",
    "seed_roles_and_permissions",
    "KnowledgeEngine", "CausalEngine",
    "ExplainabilityEngine", "Explanation",
]
