package io.github.gabrielpsmartins.phonecam

import android.Manifest
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import java.net.Inet4Address

class MainActivity : AppCompatActivity() {

    private lateinit var addressView: TextView
    private lateinit var statusView: TextView
    private lateinit var dimButton: Button

    private lateinit var server: StreamServer
    private lateinit var advertiser: ServiceAdvertiser
    private var streamer: CameraStreamer? = null
    private var dimmed = false

    private val cameraPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) startCamera() else statusView.setText(R.string.camera_denied)
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        // Tela apagada = Activity parada = CameraX fecha a câmera.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        addressView = findViewById(R.id.address)
        statusView = findViewById(R.id.status)
        dimButton = findViewById(R.id.dim)

        server = StreamServer(PORT) { msg -> runOnUiThread { statusView.text = msg } }
        server.start()

        advertiser = ServiceAdvertiser(this)
        advertiser.register("PhoneCam ${Build.MODEL}", PORT)

        addressView.text = wifiIpv4()?.let { "$it:$PORT" } ?: getString(R.string.no_wifi)

        findViewById<Button>(R.id.switchCamera).setOnClickListener {
            if (streamer?.switchCamera() != true) {
                Toast.makeText(this, "Só há uma câmera disponível", Toast.LENGTH_SHORT).show()
            }
        }
        dimButton.setOnClickListener { toggleDim() }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            cameraPermission.launch(Manifest.permission.CAMERA)
        }
    }

    override fun onDestroy() {
        streamer?.stop()
        advertiser.unregister()
        server.stop()
        super.onDestroy()
    }

    private fun startCamera() {
        if (streamer != null) return
        streamer = CameraStreamer(this, this, server).also { it.start() }
    }

    private fun toggleDim() {
        dimmed = !dimmed
        window.attributes = window.attributes.apply {
            screenBrightness = if (dimmed) 0.01f else WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE
        }
        dimButton.setText(if (dimmed) R.string.restore_screen else R.string.dim_screen)
    }

    private fun wifiIpv4(): String? {
        val cm = getSystemService(ConnectivityManager::class.java) ?: return null
        val props = cm.getLinkProperties(cm.activeNetwork) ?: return null
        return props.linkAddresses
            .map { it.address }
            .filterIsInstance<Inet4Address>()
            .firstOrNull { !it.isLoopbackAddress }
            ?.hostAddress
    }

    private companion object {
        const val PORT = 8787
    }
}
