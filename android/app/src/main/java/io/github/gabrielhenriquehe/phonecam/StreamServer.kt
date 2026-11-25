package io.github.gabrielpsmartins.phonecam

import android.util.Log
import java.io.BufferedOutputStream
import java.io.IOException
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/**
 * Servidor TCP de um cliente só. O PC conecta, recebe o handshake, o CONFIG atual e
 * depois os frames. Tudo (CONFIG e FRAME) passa pela MESMA fila, então a ordem
 * "config nova -> frames do encoder novo" é preservada ao trocar de câmera.
 *
 * Se o Wi-Fi não der conta, a fila enche: em vez de acumular atraso, descartamos
 * tudo e pedimos um keyframe novo (melhor perder 1s de vídeo do que ficar 5s atrasado).
 */
class StreamServer(
    private val port: Int,
    private val onStatus: (String) -> Unit,
) : H264Encoder.Listener {

    private val queue = LinkedBlockingQueue<ByteArray>(QUEUE_CAPACITY)

    @Volatile private var running = false
    @Volatile private var clientConnected = false
    @Volatile private var waitingKeyframe = true
    @Volatile private var encoder: H264Encoder? = null

    private var serverSocket: ServerSocket? = null
    private var client: Socket? = null
    private var worker: Thread? = null

    // estado do stream atual (protegido por `this`)
    private var width = 0
    private var height = 0
    private var rotation = 0
    private var facing: Byte = Protocol.FACING_FRONT
    private var csd: ByteArray? = null
    private var configPacket: ByteArray? = null

    fun start() {
        if (running) return
        running = true
        worker = thread(name = "stream-server") { acceptLoop() }
    }

    fun stop() {
        running = false
        runCatching { client?.close() }
        runCatching { serverSocket?.close() }
        worker?.interrupt()
    }

    // ------------------------------------------------------- chamado pela câmera

    /** Novo encoder (início ou troca de câmera). O CONFIG sai quando o SPS/PPS chegar. */
    @Synchronized
    fun onNewStream(encoder: H264Encoder, facing: Byte) {
        this.encoder = encoder
        this.width = encoder.width
        this.height = encoder.height
        this.facing = facing
        this.csd = null
        this.configPacket = null
        waitingKeyframe = true
    }

    @Synchronized
    fun onRotationChanged(degrees: Int) {
        if (degrees == rotation) return
        rotation = degrees
        rebuildConfig()
    }

    @Synchronized
    override fun onCodecConfig(csd: ByteArray) {
        if (this.csd?.contentEquals(csd) == true) return
        this.csd = csd
        rebuildConfig()
    }

    override fun onFrame(data: ByteArray, ptsUs: Long, keyframe: Boolean) {
        if (!clientConnected) return
        if (waitingKeyframe) {
            if (!keyframe) return
            waitingKeyframe = false
        }
        if (!queue.offer(Protocol.frame(data, ptsUs, keyframe))) {
            Log.w(TAG, "rede lenta: fila cheia, descartando e pedindo keyframe")
            queue.clear()
            synchronized(this) { configPacket?.let { queue.offer(it) } }
            waitingKeyframe = true
            encoder?.requestKeyFrame()
        }
    }

    private fun rebuildConfig() {
        val c = csd ?: return
        val packet = Protocol.config(width, height, rotation, facing, c)
        configPacket = packet
        if (clientConnected) queue.offer(packet)
    }

    // ------------------------------------------------------------------ rede

    private fun acceptLoop() {
        try {
            ServerSocket().use { srv ->
                srv.reuseAddress = true
                srv.bind(InetSocketAddress(port))
                serverSocket = srv
                while (running) {
                    onStatus("Aguardando o PC conectar…")
                    val socket = srv.accept()
                    client = socket
                    serve(socket)
                }
            }
        } catch (e: IOException) {
            if (running) {
                Log.e(TAG, "servidor caiu", e)
                onStatus("Erro no servidor: ${e.message}")
            }
        }
    }

    private fun serve(socket: Socket) {
        val peer = socket.inetAddress.hostAddress
        try {
            socket.tcpNoDelay = true
            val out = BufferedOutputStream(socket.getOutputStream(), 64 * 1024)
            out.write(Protocol.handshake())

            queue.clear()
            synchronized(this) {
                configPacket?.let { out.write(it) }
                waitingKeyframe = true
                clientConnected = true
            }
            out.flush()
            encoder?.requestKeyFrame() // o PC não consegue decodificar nada antes de um keyframe
            onStatus("Transmitindo para $peer")

            while (running) {
                val packet = queue.poll(500, TimeUnit.MILLISECONDS) ?: continue
                out.write(packet)
                if (queue.isEmpty()) out.flush()
            }
        } catch (e: IOException) {
            Log.i(TAG, "cliente $peer desconectou: ${e.message}")
        } catch (e: InterruptedException) {
            Thread.currentThread().interrupt()
        } finally {
            clientConnected = false
            queue.clear()
            runCatching { socket.close() }
        }
    }

    private companion object {
        const val TAG = "StreamServer"
        const val QUEUE_CAPACITY = 45 // ~1,5s a 30 fps
    }
}
