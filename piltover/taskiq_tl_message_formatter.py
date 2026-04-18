from array import array
from io import BytesIO
from typing import Any

from taskiq import TaskiqFormatter, TaskiqMessage, BrokerMessage

from piltover.tl import TLObject
from piltover.tl.base.internal import TaggedValue, TaggedVectorInst
from piltover.tl.types.internal import TaggedInt, TaggedLong, TaggedInt128, TaggedInt256, TaggedFloat, TaggedBool, \
    TaggedBytes, TaggedString, TaggedObject, TaggedVector, TaggedIntVector, TaggedBoolVector, TaggedLongVector, \
    TaggedFloatVector, TaggedBytesVector, TaggedStringVector, TaggedObjectVector
from piltover.tl.types.internal_taskiq import IntDictItem, DictItem, TaskIQMessage


def any_to_tagged_value(anything: Any) -> TaggedValue:
    if isinstance(anything, bool):
        return TaggedBool(value=anything)
    if isinstance(anything, int):
        bits = anything.bit_length()
        if bits <= 31:
            return TaggedInt(value=anything)
        if bits <= 63:
            return TaggedLong(value=anything)
        if bits <= 127:
            return TaggedInt128(value=anything)
        if bits <= 255:
            return TaggedInt256(value=anything)
        raise ValueError(f"Int too long to fit into any tl type: {bits} bits")
    if isinstance(anything, float):
        return TaggedFloat(value=anything)
    if isinstance(anything, bytes):
        return TaggedBytes(value=anything)
    if isinstance(anything, str):
        return TaggedString(value=anything)
    if isinstance(anything, TLObject):
        return TaggedObject(value=anything)
    if isinstance(anything, (list, array, tuple)):
        if not anything:
            return TaggedIntVector(vec=[])

        if isinstance(anything[0], bool):
            return TaggedVector(value=TaggedBoolVector(vec=anything))
        if isinstance(anything[0], int):
            # Surely we won't be sending plain int128 and int256, right?
            return TaggedVector(value=TaggedLongVector(vec=anything))
        if isinstance(anything[0], float):
            return TaggedVector(value=TaggedFloatVector(vec=anything))
        if isinstance(anything[0], bytes):
            return TaggedVector(value=TaggedBytesVector(vec=anything))
        if isinstance(anything[0], str):
            return TaggedVector(value=TaggedStringVector(vec=anything))
        if isinstance(anything[0], TLObject):
            return TaggedVector(value=TaggedObjectVector(vec=anything))

        raise ValueError(f"Got invalid vector item type: {anything[0].__class__.__name__!r}")
    raise ValueError(f"Got invalid type: {anything.__class__.__name__!r}")


class TLFormatter(TaskiqFormatter):
    """TL taskiq formatter."""

    def dumps(self, message: TaskiqMessage) -> BrokerMessage:
        """
        Dumps taskiq message to some broker message format.

        :param message: message to send.
        :return: Dumped message.
        """

        labels = []
        labels_types = []
        args = []
        kwargs = []

        for key, value in message.labels.items():
            labels.append(DictItem(key=key, value=any_to_tagged_value(value)))

        if message.labels_types:
            for key, value in message.labels_types.items():
                labels_types.append(IntDictItem(key=key, value=value))

        for arg in message.args:
            args.append(any_to_tagged_value(arg))

        for key, value in message.kwargs.items():
            kwargs.append(DictItem(key=key, value=any_to_tagged_value(value)))

        return BrokerMessage(
            task_id=message.task_id,
            task_name=message.task_name,
            message=TaskIQMessage(
                task_id=message.task_id,
                task_name=message.task_name,
                labels=labels,
                labels_types=labels_types,
                args=args,
                kwargs=kwargs,
            ).write(),
            labels=message.labels,
        )

    def loads(self, message: bytes) -> TaskiqMessage:
        """
        Loads json from message.

        :param message: broker's message.
        :return: parsed taskiq message.
        """

        deserialized = TaskIQMessage.read(BytesIO(message))

        labels = {}
        labels_types = None
        args = []
        kwargs = {}

        if deserialized.labels:
            for label in deserialized.labels:
                value = label.value.value
                if isinstance(value, TaggedVectorInst):
                    value = value.vec
                labels[label.key] = value

        if deserialized.labels_types:
            labels_types = {}
            for label_type in deserialized.labels_types:
                labels_types[label_type.key] = label_type.value

        if deserialized.args:
            for arg in deserialized.args:
                value = arg.value
                if isinstance(value, TaggedVectorInst):
                    value = value.vec
                args.append(value)

        if deserialized.kwargs:
            for kwarg in deserialized.kwargs:
                value = kwarg.value.value
                if isinstance(value, TaggedVectorInst):
                    value = value.vec
                kwargs[kwarg.key] = value

        return TaskiqMessage(
            task_id=deserialized.task_id,
            task_name=deserialized.task_name,
            labels=labels,
            labels_types=labels_types,
            args=args,
            kwargs=kwargs,
        )
