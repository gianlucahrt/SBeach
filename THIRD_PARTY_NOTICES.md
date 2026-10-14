# Verwendete Software und Modelle

SBeach selbst steht unter der [MIT Lizenz](LICENSE). Die folgenden Bausteine werden bei der Installation über pip oder beim ersten Start geladen. Sie sind **nicht** in diesem Repository enthalten und unterliegen ihren eigenen Lizenzen.

## Bibliotheken

| Baustein | Zweck | Lizenz |
|---|---|---|
| [mlx-whisper](https://github.com/ml-explore/mlx-examples) | Spracherkennung auf Apple Silicon | MIT |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Spracherkennung auf Intel Macs | MIT |
| [mlx-lm](https://github.com/ml-explore/mlx-lm) | Lokales Sprachmodell | MIT |
| [MLX](https://github.com/ml-explore/mlx) | Rechnen auf der Mac GPU | MIT |
| [PyObjC](https://github.com/ronaldoussoren/pyobjc) | macOS Oberfläche aus Python | MIT |
| [NumPy](https://numpy.org) | Audioverarbeitung | BSD 3 |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | Mikrofonaufnahme | MIT |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | Audio und Video lesen | BSD 2 |
| [FFmpeg](https://ffmpeg.org) (von imageio-ffmpeg geladen) | Dekodieren von Audio und Video | LGPL 2.1+ bzw. GPL, je nach Build |
| [anthropic](https://github.com/anthropics/anthropic-sdk-python) | Optionale Claude Anbindung | MIT |
| [keyring](https://github.com/jaraco/keyring) | API Schlüssel im Schlüsselbund | MIT |
| [huggingface_hub](https://github.com/huggingface/huggingface_hub) | Download der Modelle | Apache 2.0 |
| [py2app](https://github.com/ronaldoussoren/py2app) | App Bundle bauen | MIT |

## Modelle

| Modell | Zweck | Lizenz |
|---|---|---|
| [OpenAI Whisper](https://github.com/openai/whisper) (small, large v3, large v3 turbo, MLX Konvertierungen von mlx-community) | Spracherkennung | MIT |
| [Qwen 2.5 7B Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) (4 Bit MLX Konvertierung von mlx-community) | Lokale KI | Apache 2.0 |

Wer SBeach als fertige App mit eingebautem FFmpeg weitergibt, muss die Lizenzbedingungen von FFmpeg einhalten.

## Marken und Gestaltung

macOS, SF Pro und SF Symbols sind Marken bzw. Bestandteile von Apple Inc. SBeach nutzt die Systemschrift und SF Symbols ausschließlich als Bedienelemente über die Schnittstellen von macOS. App Icon und Logo sind eigene Entwürfe. Claude ist eine Marke von Anthropic. SBeach steht in keiner Verbindung zu Apple, OpenAI, Alibaba oder Anthropic.
