from s3_kolonka_gw.pcmutil import espeak_to_pcm16

pcm = espeak_to_pcm16("Привет, я колонка", "ru")
print("pcm_bytes", len(pcm), "ok", len(pcm) > 1000)
