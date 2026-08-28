// 소재·탄소 요약, 계산 근거와 생활 속 비교 UI를 구성합니다.
part of '../report_screen.dart';

String _formatMaterialValue(double value) {
  if (value % 1 == 0) {
    return value.toInt().toString();
  }
  return value.toStringAsFixed(1);
}

// 혼용률이 가장 높은 소재를 리포트의 대표 소재로 표시합니다.
String _mainMaterialLabel(Clothes item) {
  if (item.materials.isEmpty) return '소재 정보 없음';

  final sorted = item.materials.entries.toList()
    ..sort((a, b) => b.value.compareTo(a.value));

  return '${sorted.first.key.toUpperCase()} ${_formatMaterialValue(sorted.first.value)}%';
}

Widget _buildSummaryCard({
  required String title,
  required String value,
  required String subtitle,
  required IconData icon,
  required Color color,
  required Color primaryText,
  required Color secondaryText,
  required Color cardColor,
  required Color borderColor,
}) {
  return Container(
    width: double.infinity,
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(
      color: cardColor,
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: borderColor),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, color: color),
        const SizedBox(height: 12),
        Text(title, style: TextStyle(color: secondaryText, fontSize: 12)),
        const SizedBox(height: 6),
        Text(
          value,
          style: TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.bold,
            color: primaryText,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          subtitle,
          style: TextStyle(fontSize: 12, color: secondaryText, height: 1.4),
        ),
      ],
    ),
  );
}

// 계산 출처와 포함·미포함 범위를 함께 보여 주는 핵심 탄소 카드입니다.
Widget _buildProductionCarbonCard(
  Clothes item, {
  required Color primaryText,
  required Color secondaryText,
  required Color cardColor,
  required Color borderColor,
  required bool isDark,
}) {
  final sourceText =
      item.carbonFootprintSource == CarbonFootprintSource.server
      ? item.carbonFootprintMin != null && item.carbonFootprintMax != null
            ? '서버 계산값 · ${item.carbonFootprintMin!.toStringAsFixed(1)}~${item.carbonFootprintMax!.toStringAsFixed(1)} kg CO2eq 범위'
            : '서버 계산값'
      : '앱 임시 추정값';

  return Container(
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      color: cardColor,
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: borderColor),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: AppPalette.accent.withValues(alpha: isDark ? 0.22 : 0.10),
                borderRadius: BorderRadius.circular(14),
              ),
              child: const Icon(
                Icons.factory_outlined,
                color: AppPalette.accent,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '생산·제조 과정 추정값',
                    style: TextStyle(
                      color: secondaryText,
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    '${item.carbonFootprint.toStringAsFixed(1)} kg CO2eq',
                    style: TextStyle(
                      color: primaryText,
                      fontSize: 28,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    sourceText,
                    style: TextStyle(
                      color: secondaryText,
                      fontSize: 12,
                      height: 1.4,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 18),
        _buildScopeRow(
          icon: Icons.check_circle_outline,
          label: '포함',
          value: '소재, 혼용률, 의류 무게 기준',
          color: Colors.green,
          primaryText: primaryText,
          secondaryText: secondaryText,
        ),
        const SizedBox(height: 8),
        _buildScopeRow(
          icon: Icons.info_outline,
          label: '미포함',
          value: '운송, 사용, 세탁, 폐기 과정',
          color: Colors.orange,
          primaryText: primaryText,
          secondaryText: secondaryText,
        ),
        // 서버 계산일 때만 백엔드가 내려준 계산 범위·근거·출처를 보여 줍니다.
        if (item.carbonFootprintSource == CarbonFootprintSource.server &&
            (item.calculationScope != null ||
                item.calculationBasis != null ||
                item.calculationSource != null ||
                item.calculationNote != null)) ...[
          const SizedBox(height: 14),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: isDark
                  ? AppPalette.dark.background
                  : AppPalette.light.background,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: borderColor),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '계산 기준',
                  style: TextStyle(
                    color: primaryText,
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 6),
                if (item.calculationScope != null)
                  Text(
                    _calculationScopeLabel(item.calculationScope!),
                    style: TextStyle(
                      color: secondaryText,
                      fontSize: 12,
                      height: 1.5,
                    ),
                  ),
                if (item.calculationBasis != null)
                  Text(
                    item.calculationBasis!,
                    style: TextStyle(
                      color: secondaryText,
                      fontSize: 12,
                      height: 1.5,
                    ),
                  ),
                if (item.calculationSource != null)
                  Text(
                    '출처: ${item.calculationSource!}',
                    style: TextStyle(
                      color: secondaryText,
                      fontSize: 12,
                      height: 1.5,
                    ),
                  ),
                if (item.calculationNote != null)
                  Text(
                    item.calculationNote!,
                    style: TextStyle(
                      color: secondaryText,
                      fontSize: 12,
                      height: 1.5,
                    ),
                  ),
              ],
            ),
          ),
        ],
      ],
    ),
  );
}

// 서버가 내려준 계산 범위 코드를 사용자 문구로 바꿉니다.
String _calculationScopeLabel(String scope) {
  if (scope == 'material_production_estimate') {
    return '범위: 원료 및 소재 생산 단계 추정';
  }
  return '범위: $scope';
}

// 미국 EPA 환산 기준을 참고한 생활 속 탄소 비교 계수입니다. (develop d0df5a4 기준)
const double _passengerCarKgCo2EqPerKm = 0.244;
const double _smartphoneChargeKgCo2Eq = 0.0124;
const double _led10WKgCo2EqPerHour = 0.004;

// kg CO2eq를 자동차 거리·충전 횟수·전구 사용 시간으로 단순 환산합니다.
Widget _buildCarbonComparisonCard(
  Clothes item, {
  required Color primaryText,
  required Color secondaryText,
  required Color cardColor,
  required Color borderColor,
  required bool isDark,
}) {
  final carbon = item.carbonFootprint <= 0 ? 0.1 : item.carbonFootprint;
  final comparisons = [
    _CarbonComparisonData(
      icon: Icons.directions_car_filled_outlined,
      title: '자동차',
      value: '약 ${_formatImpactValue(carbon / _passengerCarKgCo2EqPerKm)} km',
    ),
    _CarbonComparisonData(
      icon: Icons.smartphone_outlined,
      title: '스마트폰',
      value: '약 ${_formatImpactValue(carbon / _smartphoneChargeKgCo2Eq)}회 충전',
    ),
    _CarbonComparisonData(
      icon: Icons.lightbulb_outline,
      title: 'LED 전구',
      value: '약 ${_formatImpactValue(carbon / _led10WKgCo2EqPerHour)}시간',
    ),
  ];

  return Container(
    width: double.infinity,
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(
      color: cardColor,
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: borderColor),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '탄소 배출량 체감',
          style: TextStyle(
            color: primaryText,
            fontSize: 16,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          '이 옷의 추정 배출량은 생활 속 기준으로 보면 아래와 비슷해요.',
          style: TextStyle(color: secondaryText, fontSize: 13, height: 1.5),
        ),
        const SizedBox(height: 14),
        LayoutBuilder(
          builder: (context, constraints) {
            final textScale = MediaQuery.textScalerOf(context).scale(1);
            final useVerticalLayout =
                constraints.maxWidth < 330 || textScale > 1.35;

            if (useVerticalLayout) {
              return Column(
                children: [
                  for (final comparison in comparisons) ...[
                    _buildComparisonTile(
                      comparison,
                      primaryText: primaryText,
                      secondaryText: secondaryText,
                      isDark: isDark,
                    ),
                    if (comparison != comparisons.last)
                      const SizedBox(height: 10),
                  ],
                ],
              );
            }

            return Row(
              children: [
                for (final comparison in comparisons) ...[
                  Expanded(
                    child: _buildComparisonTile(
                      comparison,
                      primaryText: primaryText,
                      secondaryText: secondaryText,
                      isDark: isDark,
                    ),
                  ),
                  if (comparison != comparisons.last)
                    const SizedBox(width: 10),
                ],
              ],
            );
          },
        ),
        const SizedBox(height: 12),
        Text(
          '비교값은 사용자 이해를 위한 참고 환산값이며 공식 인증값이 아닙니다. '
          '미국 EPA 환산 기준을 참고해 자동차 0.244 kg CO2eq/km, '
          '스마트폰 완전 충전 0.0124 kg CO2eq/회를 적용했습니다. '
          'LED 전구는 10W 소비전력 기준 0.004 kg CO2eq/시간으로 계산했습니다.',
          style: TextStyle(color: secondaryText, fontSize: 12, height: 1.4),
        ),
      ],
    ),
  );
}

Widget _buildCarbonScopeNotice({
  required Color primaryText,
  required Color secondaryText,
  required bool isDark,
}) {
  return Container(
    width: double.infinity,
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: isDark ? const Color(0xFF1E2A3A) : const Color(0xFFEEF4FF),
      borderRadius: BorderRadius.circular(12),
      border: Border.all(
        color: isDark ? const Color(0xFF30445F) : const Color(0xFFD9E6FF),
      ),
    ),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Icon(Icons.info_outline, color: AppPalette.accent, size: 20),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            '운송, 사용, 세탁, 폐기 과정의 배출량은 현재 수치에 포함하지 않습니다.',
            style: TextStyle(color: secondaryText, fontSize: 13, height: 1.5),
          ),
        ),
      ],
    ),
  );
}

// 탄소 계산 출처, 사용된 의류 무게와 계산 범위를 모아 표시합니다.
Widget _buildCalculationBasisCard(
  Clothes item, {
  required Color primaryText,
  required Color secondaryText,
  required Color cardColor,
  required Color borderColor,
}) {
  return Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: cardColor,
      borderRadius: BorderRadius.circular(14),
      border: Border.all(color: borderColor),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(
              Icons.fact_check_outlined,
              color: AppPalette.accent,
              size: 20,
            ),
            const SizedBox(width: 8),
            Text(
              '계산 기준',
              style: TextStyle(
                color: primaryText,
                fontSize: 15,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        _buildBasisRow(
          label: '출처',
          value: _carbonSourceLabel(item),
          primaryText: primaryText,
          secondaryText: secondaryText,
        ),
        const SizedBox(height: 8),
        _buildBasisRow(
          label: '무게',
          value: _weightBasisText(item),
          primaryText: primaryText,
          secondaryText: secondaryText,
        ),
        const SizedBox(height: 8),
        _buildBasisRow(
          label: '범위',
          value: '소재, 혼용률, 의류 무게 기준의 생산·제조 과정',
          primaryText: primaryText,
          secondaryText: secondaryText,
        ),
      ],
    ),
  );
}

Widget _buildBasisRow({
  required String label,
  required String value,
  required Color primaryText,
  required Color secondaryText,
}) {
  return Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      SizedBox(
        width: 44,
        child: Text(
          label,
          style: TextStyle(
            color: secondaryText,
            fontSize: 13,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      const SizedBox(width: 10),
      Expanded(
        child: Text(
          value,
          style: TextStyle(color: primaryText, fontSize: 13, height: 1.45),
        ),
      ),
    ],
  );
}

Widget _buildScopeRow({
  required IconData icon,
  required String label,
  required String value,
  required Color color,
  required Color primaryText,
  required Color secondaryText,
}) {
  return Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Icon(icon, color: color, size: 18),
      const SizedBox(width: 8),
      SizedBox(
        width: 52,
        child: Text(
          label,
          style: TextStyle(
            color: primaryText,
            fontSize: 13,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
      Expanded(
        child: Text(
          value,
          style: TextStyle(color: secondaryText, fontSize: 13, height: 1.4),
        ),
      ),
    ],
  );
}

Widget _buildComparisonTile(
  _CarbonComparisonData data, {
  required Color primaryText,
  required Color secondaryText,
  required bool isDark,
}) {
  return Container(
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: isDark ? const Color(0xFF2A2A2E) : const Color(0xFFF6F7FB),
      borderRadius: BorderRadius.circular(14),
    ),
    child: Row(
      children: [
        Icon(data.icon, color: AppPalette.accent, size: 22),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                data.title,
                style: TextStyle(color: secondaryText, fontSize: 12),
              ),
              const SizedBox(height: 4),
              Text(
                data.value,
                style: TextStyle(
                  color: primaryText,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}

String _formatImpactValue(double value) {
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

String _carbonSourceLabel(Clothes item) {
  return switch (item.carbonFootprintSource) {
    CarbonFootprintSource.server => '백엔드 계산값',
    CarbonFootprintSource.localEstimate => '앱 임시 추정값',
  };
}

// 실제 무게가 하나의 값인지 범위인지에 따라 계산 근거 문구를 구성합니다.
String _weightBasisText(Clothes item) {
  final minWeight = item.minWeightGram;
  final maxWeight = item.maxWeightGram;

  if (minWeight == null || maxWeight == null) {
    return '저장된 소재와 의류 유형 기준';
  }

  if ((maxWeight - minWeight).abs() <= 0.05) {
    return '실제 무게 ${_formatWeightGram(maxWeight)}g';
  }

  return '선택 무게 범위 ${_formatWeightGram(minWeight)}~${_formatWeightGram(maxWeight)}g';
}

String _formatWeightGram(double value) {
  if (value % 1 == 0) {
    return value.toInt().toString();
  }

  return value.toStringAsFixed(1);
}

// 생활 속 탄소 비교 항목의 아이콘·이름·환산값을 묶는 표시용 데이터입니다.
class _CarbonComparisonData {
  const _CarbonComparisonData({
    required this.icon,
    required this.title,
    required this.value,
  });

  final IconData icon;
  final String title;
  final String value;
}
