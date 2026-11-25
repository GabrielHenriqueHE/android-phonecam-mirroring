package io.github.gabrielhenriquehe.phonecam

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import android.view.Surface

/**
 * Encoder H.264 por hardware (MediaCodec) com entrada por Surface: a câmera desenha
 * direto no encoder, sem copiar frames pela CPU.
 */
class H264Encoder(
    val width: Int,
    val height: Int,
    bitrate: Int,
    fps: Int,
    private val listener: Listener,
) {
    interface Listener {
        /** SPS/PPS em Annex-B. Pode ser chamado mais de uma vez. */
        fun onCodecConfig(csd: ByteArray)
        fun onFrame(data: ByteArray, ptsUs: Long, keyframe: Boolean)
    }

    private val thread = HandlerThread("h264-encoder").apply { start() }
    private val handler = Handler(thread.looper)
    private val codec: MediaCodec = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)

    @Volatile private var released = false

    /** Surface que deve ser entregue ao CameraX. */
    val inputSurface: Surface = run {
        val format = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, width, height).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
            setInteger(MediaFormat.KEY_BIT_RATE, bitrate)
            setInteger(MediaFormat.KEY_FRAME_RATE, fps)
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1) // keyframe a cada 1s: recupera rápido de perda
            setInteger(MediaFormat.KEY_PRIORITY, 0) // 0 = tempo real
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                setInteger(MediaFormat.KEY_MAX_B_FRAMES, 0) // B-frames = latência
            }
        }
        try {
            codec.setCallback(Callback(), handler) // precisa vir antes do configure
            codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
            codec.createInputSurface().also { codec.start() }
        } catch (e: Exception) {
            codec.release()
            thread.quitSafely()
            throw e
        }
    }

    fun requestKeyFrame() {
        handler.post {
            if (released) return@post
            try {
                codec.setParameters(Bundle().apply { putInt(MediaCodec.PARAMETER_KEY_REQUEST_SYNC_FRAME, 0) })
            } catch (e: IllegalStateException) {
                Log.w(TAG, "requestKeyFrame falhou", e)
            }
        }
    }

    /** Chamar só depois que o CameraX avisar que parou de usar a [inputSurface]. */
    fun release() {
        handler.post {
            if (released) return@post
            released = true
            try { codec.stop() } catch (e: IllegalStateException) { Log.w(TAG, "stop", e) }
            codec.release()
            inputSurface.release()
            thread.quitSafely()
        }
    }

    private inner class Callback : MediaCodec.Callback() {
        override fun onInputBufferAvailable(codec: MediaCodec, index: Int) {
            // entrada por Surface: não há buffers de entrada
        }

        override fun onOutputBufferAvailable(codec: MediaCodec, index: Int, info: MediaCodec.BufferInfo) {
            if (released) return
            try {
                val buffer = codec.getOutputBuffer(index)
                if (buffer != null && info.size > 0) {
                    val bytes = ByteArray(info.size)
                    buffer.position(info.offset)
                    buffer.limit(info.offset + info.size)
                    buffer.get(bytes)
                    if (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0) {
                        listener.onCodecConfig(bytes)
                    } else {
                        val key = info.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME != 0
                        listener.onFrame(bytes, info.presentationTimeUs, key)
                    }
                }
                codec.releaseOutputBuffer(index, false)
            } catch (e: IllegalStateException) {
                Log.w(TAG, "buffer de saída após release", e)
            }
        }

        override fun onOutputFormatChanged(codec: MediaCodec, format: MediaFormat) {
            // Alguns aparelhos só expõem SPS/PPS aqui (csd-0 / csd-1), já em Annex-B.
            val sps = format.getByteBuffer("csd-0")?.duplicate() ?: return
            val pps = format.getByteBuffer("csd-1")?.duplicate()
            val spsLen = sps.remaining()
            val out = ByteArray(spsLen + (pps?.remaining() ?: 0))
            sps.get(out, 0, spsLen)
            if (pps != null) pps.get(out, spsLen, pps.remaining())
            listener.onCodecConfig(out)
        }

        override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) {
            Log.e(TAG, "erro no encoder", e)
        }
    }

    private companion object {
        const val TAG = "H264Encoder"
    }
}
