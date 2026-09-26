"""FSM state groups for multi-step flows."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class SetPin(StatesGroup):
    waiting_pin = State()


class Withdraw(StatesGroup):
    waiting_asset = State()
    waiting_amount = State()
    waiting_address = State()
    waiting_pin = State()


class Deposit(StatesGroup):
    waiting_asset = State()
    waiting_amount = State()


class CreateOffer(StatesGroup):
    waiting_asset = State()
    waiting_amount = State()
    waiting_price = State()
    waiting_payment = State()


class TakeOffer(StatesGroup):
    waiting_amount = State()
