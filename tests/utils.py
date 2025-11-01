def color_is_near(expected: tuple[int, int, int], actual: tuple[int, int, int], error: float = 0.05) -> bool:
    err_val = 0xff * error
    expected_min = (max(0x00, int(exp - err_val)) for exp in expected)
    expected_max = (min(0xff, int(exp + err_val)) for exp in expected)

    for exp_min, exp_max, act in zip(expected_min, expected_max, actual):
        if act < exp_min or act > exp_max:
            return False

    return True
