from s3_kolonka_gw.pcmutil import piper_to_pcm16

pcm = piper_to_pcm16("Привет, я колонка", "/opt/s3-kolonka-gw/voices/ru_RU-irina-medium.onnx")
print("pcm_bytes", len(pcm), "ok", len(pcm) > 10000)
