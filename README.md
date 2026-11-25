# PhoneCam

Usa a câmera do celular Android como **webcam no Linux**, por Wi-Fi. Não precisa de conta, não tem anúncios e não depende de internet. O Meet, o Zoom e o OBS enxergam como uma câmera comum: `/dev/video10`, com o nome "PhoneCam".

```
┌──────────── Android ────────────┐          Wi-Fi / TCP :8787          ┌──────────── Linux ─────────────┐
│ CameraX Preview                 │                                      │ phonecam (Python)              │
│   └─▶ Surface do MediaCodec     │   PCAM v1: CONFIG(SPS/PPS, rot)      │   PyAV decodifica H.264        │
│        └─▶ H.264 (hardware)     │ ───────────────────────────────────▶ │   rotaciona + letterbox        │
│             └─▶ StreamServer    │            FRAME(H.264 AU)           │   pyvirtualcam ─▶ v4l2loopback │
│ NSD anuncia _phonecam._tcp      │ ◀─ mDNS: PC acha o celular sozinho ─ │        └─▶ /dev/video10 ─▶ Meet│
└─────────────────────────────────┘                                      └────────────────────────────────┘
```

## Por que é diferente dos apps prontos

- **Zero cópia no celular.** A câmera desenha direto na Surface do encoder por hardware, sem passar frames pela CPU nem por JPEG.
- **Latência controlada.** Não há B-frames, e o PC decodifica cada access unit assim que ele chega (sem o parser do FFmpeg segurar um frame). Se o Wi-Fi engasgar, o celular **descarta e pede um keyframe** em vez de acumular atraso.
- **A webcam nunca some do Meet.** A câmera virtual tem tamanho fixo e recebe frames o tempo todo. Se o celular desconectar, ela mostra uma tela cinza e reconecta sozinha. Girar o aparelho ou trocar de câmera vira letterbox, sem mudar o formato do dispositivo.
- **Protocolo próprio e documentado** em [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

## Uso

### 1. PC: webcam virtual (uma vez só)

```bash
./scripts/setup-v4l2loopback.sh
```

O script instala o `v4l2loopback` e cria `/dev/video10` com `exclusive_caps=1`. Sem essa opção, o Chrome não lista a câmera. O dispositivo passa a ser criado automaticamente a cada boot.

### 2. PC: cliente

```bash
python3 -m venv ~/.venvs/phonecam
~/.venvs/phonecam/bin/pip install ./desktop
~/.venvs/phonecam/bin/phonecam            # acha o celular via mDNS
~/.venvs/phonecam/bin/phonecam --host 192.168.0.42   # ou pelo IP que aparece no app
```

O PyAV já vem com o FFmpeg embutido, então não é preciso instalar o ffmpeg no sistema.

Opções úteis: `--size 1920x1080`, `--rotate 90` (força a rotação), `--mirror`, `--null` (testa a recepção sem a webcam virtual) e `-v`.

### 3. Celular

Instale o APK (ver [Build do APK](#build-do-apk)), abra o app e deixe-o aberto. Ele mostra `IP:8787` e o status. **Não bloqueie a tela**, porque o Android fecha a câmera. Use o botão "Escurecer tela" para poupar bateria.

### 4. Meet

Abra Configurações > Vídeo > **PhoneCam**.

## Build do APK

- **Pelo Android Studio:** abra a pasta `android/` e use *Build > Build APK(s)*.
- **Pela linha de comando:** com o Android SDK instalado, rode `cd android && ./gradlew assembleDebug`. O APK sai em `android/app/build/outputs/apk/debug/`.
- **Sem instalar nada:** faça push para o GitHub. O workflow `.github/workflows/android.yml` gera o APK e o anexa como artefato da execução.

## Desenvolvimento

```bash
cd desktop
pip install -e ".[dev]"
pytest                                  # protocolo, rotação/letterbox, fluxo completo com celular falso, mDNS
python tools/fake_phone.py --rotation 90 --mdns   # "celular" de mentira gerando H.264
phonecam --null                         # em outro terminal
```

O `fake_phone.py` fala exatamente o mesmo protocolo que o app. Com ele dá para desenvolver o lado do PC sem o celular.

## Solução de problemas

| sintoma | causa provável |
|---|---|
| A PhoneCam não aparece no Meet | O módulo foi carregado sem `exclusive_caps=1`. Rode o script de novo e reabra o navegador. |
| `modprobe: Key was rejected by service` | Secure Boot está ativo: conclua o "Enroll MOK" no próximo boot. |
| `procurando o celular...` não acaba | O roteador ou o firewall bloqueia multicast. Use `--host IP`. |
| A imagem fica de lado | Use `--rotate 0/90/180/270`. |
| Fica cinza depois de um tempo | A tela do celular apagou ou o app saiu do primeiro plano. |

## Limitações (v0.1)

- Só Linux no desktop. No Windows, falta um backend de câmera virtual.
- Só vídeo, sem áudio.
- Não há autenticação: qualquer dispositivo na mesma rede pode conectar na porta 8787. Use em redes confiáveis.
