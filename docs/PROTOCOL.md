# Protocolo PhoneCam v1

O **celular é o servidor** TCP, na porta `8787`. O PC conecta nele. O celular também se anuncia por mDNS como `_phonecam._tcp`. O fluxo é de mão única (celular → PC), e todos os inteiros são **big-endian**.

## Handshake

Assim que a conexão abre, o celular envia:

| campo   | tipo     | valor    |
|---------|----------|----------|
| magic   | 4 bytes  | `PCAM`   |
| version | u8       | `1`      |

## Pacotes

```
u8  type
u32 payload_len
... payload
```

O cliente **ignora** os tipos que não conhece. Assim dá para adicionar pacotes novos (áudio, por exemplo) sem quebrar clientes antigos.

### `1` CONFIG

| campo     | tipo  | descrição                                                     |
|-----------|-------|---------------------------------------------------------------|
| width     | u16   | largura do buffer codificado                                  |
| height    | u16   | altura do buffer codificado                                   |
| rotation  | u16   | 0/90/180/270: graus no sentido **horário** para deixar a imagem em pé |
| facing    | u8    | 0 = traseira, 1 = frontal                                     |
| csd       | resto | SPS + PPS em Annex-B (`00 00 00 01 …`)                        |

O celular reenvia o CONFIG quando muda a câmera (encoder novo) ou a rotação do aparelho. O CONFIG sempre vem **antes** dos frames que dependem dele, porque os dois passam pela mesma fila.

### `2` FRAME

| campo  | tipo  | descrição                              |
|--------|-------|----------------------------------------|
| flags  | u8    | bit 0 = keyframe (IDR)                 |
| pts_us | i64   | timestamp de apresentação (µs)         |
| data   | resto | um access unit H.264 completo, Annex-B |

## Regras de robustez

- Quando um cliente conecta, o celular pede um keyframe ao encoder e descarta frames até que ele saia.
- Se a fila de envio enche (Wi-Fi lento), o celular descarta tudo, reenvia o CONFIG e espera o próximo keyframe. A ideia é perder um trecho de vídeo em vez de acumular atraso.
- O cliente desktop prefixa SPS/PPS a cada keyframe. Se a decodificação der erro, ele descarta frames até o próximo keyframe.
