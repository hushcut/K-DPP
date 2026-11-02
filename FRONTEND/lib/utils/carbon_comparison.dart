// 탄소량을 생활 기준으로 옮기는 환산입니다. 홈과 리포트가 같은 숫자를 보이도록 함께 씁니다.

// 미국 EPA 환산 기준을 참고한 생활 속 탄소 비교 계수입니다. (develop d0df5a4 기준)
const double passengerCarKgCo2EqPerKm = 0.244;

String formatImpactValue(double value) {
  if (!value.isFinite || value <= 0) return '1';

  if (value < 10) {
    final rounded = value.toStringAsFixed(1);
    return rounded.endsWith('.0')
        ? rounded.substring(0, rounded.length - 2)
        : rounded;
  }

  if (value < 100) {
    return value.round().toString();
  }

  return ((value / 10).round() * 10).toString();
}
