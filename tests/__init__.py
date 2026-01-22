"""
Test Suite for Enterprise STORM System

This package contains comprehensive unit and integration tests
for the STORM pipeline, including:

- Database connectivity and model mapping tests
- Repository CRUD operation tests
- Service layer logic tests
- Async session management tests

Test Structure:
    tests/
    ├── conftest.py           - Shared fixtures for all tests
    ├── integration/          - Tests requiring real DB connection
    │   ├── test_db_connection.py
    │   └── test_repositories.py
    └── unit/                 - Isolated logic tests with mocks
        └── test_generation_service.py

Usage:
    # Run all tests
    pytest tests/ -v
    
    # Run only integration tests
    pytest tests/integration/ -v
    
    # Run only unit tests
    pytest tests/unit/ -v
    
    # Run with coverage
    pytest tests/ --cov=src --cov-report=html

Requirements:
    - pytest>=7.4.0
    - pytest-asyncio>=0.21.0
    - pytest-mock>=3.11.0
    - pytest-cov>=4.1.0 (optional, for coverage reports)

Author: Enterprise Architecture Team
Created: 2026-01-21
"""
