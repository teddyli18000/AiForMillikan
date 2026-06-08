from millikan_ai.compute import select_compute_backend


def test_auto_compute_backend_falls_back_to_cpu_without_opencv_cuda():
    backend = select_compute_backend("auto", cuda_device_count=lambda: 0)

    assert backend.name == "cpu"
    assert backend.gpu_available is False
    assert backend.fallback_reason == "opencv_cuda_unavailable"


def test_auto_compute_backend_selects_opencv_cuda_when_available():
    backend = select_compute_backend("auto", cuda_device_count=lambda: 1)

    assert backend.name == "opencv_cuda"
    assert backend.gpu_available is True
    assert backend.device_index == 0
