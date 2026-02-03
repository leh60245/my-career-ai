import logging
from abc import ABC
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Base

logger = logging.getLogger(__name__)

# Type variable for model classes
T = TypeVar("T", bound=Base)


class RepositoryException(Exception):
    """Base exception for repository operations."""

    pass


class EntityNotFound(RepositoryException):
    """Raised when entity is not found."""

    pass


class DuplicateEntity(RepositoryException):
    """Raised when duplicate entity creation is attempted."""

    pass


class RepositoryError(RepositoryException):
    """Generic repository operation error."""

    pass


class BaseRepository(ABC, Generic[T]):
    def __init__(self, model: type[T], session: AsyncSession) -> None:
        if model is None:
            raise ValueError("Model cannot be None")
        if session is None:
            raise ValueError("AsyncSession cannot be None")

        self.model: type[T] = model
        self.session: AsyncSession = session
        logger.debug(f"Initialized {self.__class__.__name__} for model {self.model.__name__}")

    async def get(self, id: Any) -> T | None:
        try:
            query = select(self.model).where(self.model.id == id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting {self.model.__name__} by id {id}: {e}")
            raise RepositoryError(f"Failed to get entity: {e}") from e

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: str | None = None,
        ascending: bool = True,
    ) -> Sequence[T]:
        stmt = select(self.model)

        # Add ordering
        if order_by:
            if not hasattr(self.model, order_by):
                # 개발자 실수이므로 ValueError 등을 던지거나 무시
                logger.warning(f"Invalid order_by column: {order_by}")
            else:
                order_col = getattr(self.model, order_by)
                stmt = stmt.order_by(order_col.asc()) if ascending else stmt.order_by(order_col.desc())

        # Pagination
        stmt = stmt.offset(skip).limit(limit)

        try:
            result = await self.session.execute(stmt)
            return result.scalars().all()

        except Exception as e:
            logger.error(f"Error listing {self.model.__name__}: {e}")
            raise RepositoryError(f"Failed to list entities: {e}") from e

    async def create(self, obj_in: T | dict[str, Any]) -> T:
        db_obj = self.model(**obj_in) if isinstance(obj_in, dict) else obj_in
        self.session.add(db_obj)

        try:
            await self.session.flush()
            await self.session.refresh(db_obj)
            return db_obj

        except IntegrityError as e:
            pgcode = getattr(e.orig, "pgcode", None) or getattr(e.orig, "sqlstate", None)

            if pgcode == "23505" or "unique" in str(e).lower():  # PostgreSQL unique violation code
                logger.warning(f"Duplicate entity detected: {e}")
                raise DuplicateEntity(f"{self.model.__name__} already exists.") from e

            logger.error(f"Integrity Error creating {self.model.__name__}: {e}")
            raise RepositoryError(f"Database integrity error: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error creating {self.model.__name__}: {e}")
            raise RepositoryError(f"Failed to create entity: {e}") from e

    async def update(self, id: Any, obj_in: dict[str, Any] | Any) -> T:
        update_data = (
            obj_in
            if isinstance(obj_in, dict)
            else obj_in.model_dump(exclude_unset=True)
            if hasattr(obj_in, "model_dump")
            else obj_in.__dict__
        )
        try:
            db_obj = await self.get(id)

            if db_obj is None:
                raise EntityNotFound(f"{self.model.__name__} with id {id} not found")

            for key, value in update_data.items():
                if hasattr(db_obj, key):
                    setattr(db_obj, key, value)

            self.session.add(db_obj)
            await self.session.flush()
            await self.session.refresh(db_obj)

            return db_obj

        except EntityNotFound:
            raise
        except Exception as e:
            logger.error(f"Error updating {self.model.__name__} with id {id}: {e}")
            raise RepositoryError(f"Failed to update entity: {e}") from e

    async def delete(self, id: Any) -> bool:
        try:
            stmt = select(self.model).where(self.model.id == id)
            result = await self.session.execute(stmt)
            db_obj = result.scalar_one_or_none()

            if not db_obj:
                logger.debug(f"{self.model.__name__} with id {id} not found for deletion")
                return False

            await self.session.delete(db_obj)
            await self.session.flush()
            return True

        except Exception as e:
            logger.error(f"Error deleting {self.model.__name__} with id {id}: {e}")
            raise RepositoryError(f"Failed to delete entity: {e}") from e
