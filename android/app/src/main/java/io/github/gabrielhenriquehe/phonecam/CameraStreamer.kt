package io.github.gabrielhenriquehe.phonecam

import android.content.Context
import android.util.Log
import android.util.Size
import android.view.OrientationEventListener
import android.view.Surface
import androidx.camera.core.CameraSelector
import androidx.camera.core.Preview
import androidx.camera.core.SurfaceRequest
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner

/**
 * Liga a câmera (CameraX) direto no encoder: o use case `Preview` desenha na Surface
 * de entrada do MediaCodec em vez de numa tela.
 */
class CameraStreamer(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val server: StreamServer,
) {
    private val mainExecutor = ContextCompat.getMainExecutor(context)
    private var provider: ProcessCameraProvider? = null
    private var preview: Preview? = null
    private var lensFacing = CameraSelector.LENS_FACING_FRONT

    /** Segue a orientação FÍSICA do aparelho (a Activity está travada em retrato). */
    private val orientationListener = object : OrientationEventListener(context) {
        override fun onOrientationChanged(orientation: Int) {
            if (orientation == ORIENTATION_UNKNOWN) return
            val rotation = when (orientation) {
                in 45 until 135 -> Surface.ROTATION_270
                in 135 until 225 -> Surface.ROTATION_180
                in 225 until 315 -> Surface.ROTATION_90
                else -> Surface.ROTATION_0
            }
            preview?.targetRotation = rotation
        }
    }

    fun start() {
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            provider = future.get()
            bind()
        }, mainExecutor)
        orientationListener.enable()
    }

    fun stop() {
        orientationListener.disable()
        provider?.unbindAll() // dispara o callback que libera o encoder
    }

    /** Alterna frontal/traseira. Retorna false se o aparelho não tiver a outra. */
    fun switchCamera(): Boolean {
        val target = if (lensFacing == CameraSelector.LENS_FACING_FRONT)
            CameraSelector.LENS_FACING_BACK else CameraSelector.LENS_FACING_FRONT
        val p = provider ?: return false
        val available = runCatching {
            p.hasCamera(CameraSelector.Builder().requireLensFacing(target).build())
        }.getOrDefault(false)
        if (!available) return false
        lensFacing = target
        bind()
        return true
    }

    private fun bind() {
        val p = provider ?: return
        val resolution = ResolutionSelector.Builder()
            .setResolutionStrategy(
                ResolutionStrategy(TARGET_SIZE, ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER)
            )
            .build()

        val newPreview = Preview.Builder()
            .setResolutionSelector(resolution)
            .build()
        newPreview.setSurfaceProvider(mainExecutor, Preview.SurfaceProvider { request -> onSurfaceRequested(request) })

        val selector = CameraSelector.Builder().requireLensFacing(lensFacing).build()
        try {
            p.unbindAll()
            p.bindToLifecycle(lifecycleOwner, selector, newPreview)
            preview = newPreview
        } catch (e: Exception) {
            Log.e(TAG, "falha ao abrir a câmera", e)
        }
    }

    private fun onSurfaceRequested(request: SurfaceRequest) {
        val size = request.resolution
        val encoder = try {
            H264Encoder(size.width, size.height, BITRATE, FPS, server)
        } catch (e: Exception) {
            Log.e(TAG, "encoder não aceitou ${size.width}x${size.height}", e)
            request.willNotProvideSurface()
            return
        }
        Log.i(TAG, "stream ${size.width}x${size.height}")

        val facing = if (lensFacing == CameraSelector.LENS_FACING_FRONT)
            Protocol.FACING_FRONT else Protocol.FACING_BACK
        server.onNewStream(encoder, facing)

        // Graus (horário) para deixar o buffer em pé; muda quando giramos o aparelho.
        request.setTransformationInfoListener(mainExecutor) { info ->
            server.onRotationChanged(info.rotationDegrees)
        }
        // O callback chega quando a câmera para de usar a Surface: só aí liberamos.
        request.provideSurface(encoder.inputSurface, mainExecutor) { encoder.release() }
    }

    private companion object {
        const val TAG = "CameraStreamer"
        val TARGET_SIZE = Size(1280, 720)
        const val FPS = 30
        const val BITRATE = 4_000_000 // 4 Mbps: folgado para 720p num Wi-Fi doméstico
    }
}
