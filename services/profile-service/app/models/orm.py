from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("UserProfile", back_populates="user", uselist=False)
    interests = relationship("UserInterest", back_populates="user", cascade="all, delete-orphan")
    preferences = relationship("UserPreferences", back_populates="user", uselist=False)
    photos = relationship("UserPhoto", back_populates="user", cascade="all, delete-orphan")

    # Stats where this user is the candidate being viewed
    received_interactions = relationship(
        "CandidateBehavioralStats",
        foreign_keys="CandidateBehavioralStats.candidate_id",
        back_populates="candidate",
    )
    # Stats where this user is the one viewing
    given_interactions = relationship(
        "CandidateBehavioralStats",
        foreign_keys="CandidateBehavioralStats.viewer_id",
        back_populates="viewer",
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String(20), nullable=False)
    city = Column(String(100), nullable=False)
    bio = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="profile")


class UserInterest(Base):
    __tablename__ = "user_interests"
    __table_args__ = (UniqueConstraint("user_id", "interest"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    interest = Column(String(100), nullable=False)

    user = relationship("User", back_populates="interests")


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    min_age = Column(Integer, default=18, nullable=False)
    max_age = Column(Integer, default=99, nullable=False)
    # None means no preference
    preferred_gender = Column(String(20), nullable=True)

    user = relationship("User", back_populates="preferences")


class UserPhoto(Base):
    __tablename__ = "user_photos"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    url = Column(String(500), nullable=False)
    object_key = Column(String(500), nullable=False, server_default="")
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="photos")


class CandidateBehavioralStats(Base):
    """One row per (viewer, candidate) pair — tracks all interactions between them."""

    __tablename__ = "candidate_behavioral_stats"
    __table_args__ = (UniqueConstraint("viewer_id", "candidate_id"),)

    id = Column(Integer, primary_key=True)
    viewer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    candidate_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    likes_given = Column(Integer, default=0, nullable=False)
    skips_given = Column(Integer, default=0, nullable=False)
    is_matched = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    viewer = relationship("User", foreign_keys=[viewer_id], back_populates="given_interactions")
    candidate = relationship("User", foreign_keys=[candidate_id], back_populates="received_interactions")


class UserCandidateRatingSnapshot(Base):
    """
    Pre-computed Level 3 rating snapshot for a viewer-candidate pair.
    Populated by Celery tasks (recompute_combined_snapshots) every hour.
    Allows the recommendation service to rank candidates without heavy
    real-time computation on each API request.
    """

    __tablename__ = "user_candidate_ratings_snapshot"
    __table_args__ = (UniqueConstraint("viewer_id", "candidate_id"),)

    id = Column(Integer, primary_key=True)
    viewer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    candidate_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    primary_score = Column(Float, nullable=False, default=0.0)
    behavioral_score = Column(Float, nullable=False, default=0.5)
    combined_score = Column(Float, nullable=False, default=0.0)
    computed_at = Column(DateTime, default=datetime.utcnow)
