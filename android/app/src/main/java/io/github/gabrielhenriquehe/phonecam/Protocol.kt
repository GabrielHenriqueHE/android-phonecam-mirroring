package io.github.gabrielpsmartins.phonecam

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Protocolo de fio (ver docs/PROTOCOL.md). Tudo big-endian.
 *
 *   handshake : "PCAM" + u8 version
 *   packet    : u8 type + u32 payload_len + payload
 *   CONFIG(1) : u16 width, u16 height, u16 rotation, u8 facing, bytes csd (SPS/PPS Annex-B)
 *   FRAME (2) : u8 flags (bit0 = keyframe), i64 pts_us, bytes access_unit (Annex-B)
 */
object Protocol {
    const val VERSION: Byte = 1
    private const val TYPE_CONFIG: Byte = 1
    private const val TYPE_FRAME: Byte = 2
    private const val FLAG_KEYFRAME = 0x01

    const val FACING_BACK: Byte = 0
    const val FACING_FRONT: Byte = 1

    fun handshake(): ByteArray =
        byteArrayOf('P'.code.toByte(), 'C'.code.toByte(), 'A'.code.toByte(), 'M'.code.toByte(), VERSION)

    fun config(width: Int, height: Int, rotation: Int, facing: Byte, csd: ByteArray): ByteArray {
        val payload = 2 + 2 + 2 + 1 + csd.size
        return ByteBuffer.allocate(5 + payload).order(ByteOrder.BIG_ENDIAN)
            .put(TYPE_CONFIG)
            .putInt(payload)
            .putShort(width.toShort())
            .putShort(height.toShort())
            .putShort(rotation.toShort())
            .put(facing)
            .put(csd)
            .array()
    }

    fun frame(data: ByteArray, ptsUs: Long, keyframe: Boolean): ByteArray {
        val payload = 1 + 8 + data.size
        return ByteBuffer.allocate(5 + payload).order(ByteOrder.BIG_ENDIAN)
            .put(TYPE_FRAME)
            .putInt(payload)
            .put((if (keyframe) FLAG_KEYFRAME else 0).toByte())
            .putLong(ptsUs)
            .put(data)
            .array()
    }
}
