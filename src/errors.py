"""Содержит независимые от инфраструктуры ошибки MiniKV."""


class MiniKVError(Exception):
    """
    Служит базовой ошибкой предметной области MiniKV.

    Attributes:
        Не предусмотрены.

    Fallbacks:
        Не предусмотрены.
    """


class KeyNotFoundError(MiniKVError):
    """
    Сообщает об отсутствии запрошенного ключа.

    Attributes:
        Не предусмотрены.

    Fallbacks:
        Не предусмотрены.
    """


class PersistenceError(MiniKVError):
    """
    Сообщает об ошибке чтения или сохранения состояния.

    Attributes:
        Не предусмотрены.

    Fallbacks:
        Не предусмотрены.
    """


class NodeUnavailableError(MiniKVError):
    """
    Сообщает о недоступности узла базы данных.

    Attributes:
        Не предусмотрены.

    Fallbacks:
        Не предусмотрены.
    """


class ReplicationError(MiniKVError):
    """
    Сообщает о нарушении порядка или состояния репликации.

    Attributes:
        Не предусмотрены.

    Fallbacks:
        Не предусмотрены.
    """
