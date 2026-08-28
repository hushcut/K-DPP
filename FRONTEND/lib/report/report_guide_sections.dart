// 소재별 관리 팁, 폐기 안내와 관리 정보 UI를 구성합니다.
part of '../report_screen.dart';

bool _hasMaterial(Clothes item, List<String> keywords) {
  final lowerKeys = item.materials.keys.map((e) => e.toLowerCase()).toList();
  return lowerKeys.any(
    (key) => keywords.any((keyword) => key.contains(keyword)),
  );
}

// 소재 키워드와 라벨 지침을 조합해 의류별 세탁·관리 문구를 만듭니다.
List<String> _buildCareTips(Clothes item) {
  final tips = <String>[];

  if (_hasMaterial(item, ['cotton', 'linen'])) {
    tips.add('면/린넨 계열은 미지근한 물 세탁과 자연 건조가 수명 유지에 도움이 됩니다.');
  }

  if (_hasMaterial(item, ['polyester', 'nylon'])) {
    tips.add('합성섬유는 높은 온도에 약할 수 있어 건조기 사용을 줄이는 것이 좋습니다.');
  }

  if (_hasMaterial(item, ['wool', 'silk'])) {
    tips.add('울/실크 계열은 마찰과 열에 민감하므로 중성세제와 약한 세탁 코스를 권장합니다.');
  }

  if (_hasMaterial(item, ['polyurethane', 'spandex'])) {
    tips.add('신축성 섬유가 포함된 의류는 비틀어 짜기보다 눌러서 물기를 제거하는 편이 안전합니다.');
  }

  tips.add('착용 후 바로 보관하기보다 잠시 통풍시키고, 세탁 전에는 케어 라벨의 온도와 건조 지침을 먼저 확인하세요.');

  if (item.careInstruction.isNotEmpty) {
    tips.add('라벨 지침: ${item.careInstruction}');
  }

  return tips;
}

// 주요 소재 특성에 따라 보관 시 주의할 점을 선택합니다.
String _buildStorageTip(Clothes item) {
  if (_hasMaterial(item, ['wool', 'knit'])) {
    return '니트/울 계열은 걸어두기보다 접어서 보관하면 늘어남을 줄일 수 있습니다.';
  }

  if (_hasMaterial(item, ['silk'])) {
    return '실크 계열은 직사광선을 피해 통풍이 되는 곳에 보관하는 것이 좋습니다.';
  }

  if (_hasMaterial(item, ['linen', 'cotton'])) {
    return '면/린넨 계열은 충분히 건조한 뒤 보관하면 냄새와 곰팡이 위험을 줄일 수 있습니다.';
  }

  return '착용 후 바로 보관하기보다 잠시 통풍시킨 뒤 정리하면 의류 컨디션 유지에 도움이 됩니다.';
}

// 천연·합성 소재 여부에 맞춰 재사용과 지역 배출 기준 확인 순서를 안내합니다.
String _buildDisposalGuide(Clothes item) {
  if (_hasMaterial(item, ['cotton', 'linen', 'wool'])) {
    return '천연섬유 비중이 높다면 오염과 손상 정도를 직접 확인한 뒤 의류수거함, 기부, 업사이클링 활용 가능성을 검토해 보세요.';
  }

  if (_hasMaterial(item, ['polyester', 'nylon', 'polyurethane'])) {
    return '혼방·합성섬유 의류는 지역 분리배출 기준을 먼저 확인하고, 재사용이 어렵다고 판단될 때 의류 수거 체계에 맞춰 배출하세요.';
  }

  return '의류의 오염과 손상 정도를 직접 확인한 뒤 재사용, 기부, 지역 의류 수거 기준을 순서대로 검토해 보세요.';
}

void _showDisposalBottomSheet(
  BuildContext context,
  Clothes item,
  String disposalGuide,
) {
  final isDark = Theme.of(context).brightness == Brightness.dark;
  final palette = AppPalette.of(context);
  final backgroundColor = isDark ? const Color(0xFF121212) : Colors.white;
  final primaryText = palette.textPrimary;
  final secondaryText = isDark ? const Color(0xFFD1D1D6) : Colors.black87;

  showModalBottomSheet(
    context: context,
    showDragHandle: true,
    backgroundColor: backgroundColor,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    builder: (context) {
      return SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '권장 폐기 및 재사용 가이드',
                style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  color: primaryText,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                disposalGuide,
                style: TextStyle(
                  fontSize: 14,
                  height: 1.6,
                  color: secondaryText,
                ),
              ),
              const SizedBox(height: 16),
              _buildBottomSheetBullet(
                '상태가 양호하면 중고 거래 또는 기부를 먼저 검토하세요.',
                secondaryText,
              ),
              _buildBottomSheetBullet(
                '혼방 소재는 지역 의류 수거 기준을 확인한 뒤 배출하세요.',
                secondaryText,
              ),
              _buildBottomSheetBullet(
                '오염이 심한 경우 재사용 가능 여부를 먼저 판단한 뒤 처리하세요.',
                secondaryText,
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                height: 48,
                child: ElevatedButton(
                  onPressed: () => Navigator.pop(context),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.green,
                  ),
                  child: const Text(
                    '확인했어요',
                    style: TextStyle(color: Colors.white),
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    },
  );
}

Widget _buildBottomSheetBullet(String text, Color textColor) {
  return Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(top: 5),
          child: Icon(Icons.circle, size: 8, color: Colors.green),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            text,
            style: TextStyle(fontSize: 14, height: 1.5, color: textColor),
          ),
        ),
      ],
    ),
  );
}

Widget _buildGuideSection({
  required String title,
  required IconData icon,
  required Color color,
  required List<String> children,
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
        Row(
          children: [
            Icon(icon, color: color),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                title,
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.bold,
                  color: primaryText,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 14),
        ...children.map(
          (tip) => Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Padding(
                  padding: EdgeInsets.only(top: 6),
                  child: Icon(
                    Icons.circle,
                    size: 8,
                    color: AppPalette.accent,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    tip,
                    style: TextStyle(
                      fontSize: 14,
                      height: 1.5,
                      color: secondaryText,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    ),
  );
}

Widget _buildHistoryRow(
  String title,
  String value, {
  required Color primaryText,
  required Color secondaryText,
}) {
  return LayoutBuilder(
    builder: (context, constraints) {
      final textScale = MediaQuery.textScalerOf(context).scale(1);
      final useVerticalLayout =
          constraints.maxWidth < 320 || textScale > 1.35;
      final titleWidget = Text(
        title,
        style: TextStyle(color: secondaryText, fontSize: 15),
      );
      final valueWidget = Text(
        value,
        style: TextStyle(
          fontWeight: FontWeight.bold,
          fontSize: 15,
          height: 1.5,
          color: primaryText,
        ),
        textAlign: useVerticalLayout ? TextAlign.left : TextAlign.right,
      );

      return Padding(
        padding: const EdgeInsets.only(bottom: 10.0),
        child: useVerticalLayout
            ? Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  titleWidget,
                  const SizedBox(height: 4),
                  valueWidget,
                ],
              )
            : Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(width: 100, child: titleWidget),
                  Expanded(child: valueWidget),
                ],
              ),
      );
    },
  );
}

Widget _buildTagChip({
  required IconData icon,
  required String label,
  required bool isDark,
}) {
  final bgColor = isDark ? const Color(0xFF232A45) : const Color(0xFFEEF1FF);

  return ConstrainedBox(
    constraints: const BoxConstraints(maxWidth: 220),
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: AppPalette.accent),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              label,
              softWrap: true,
              style: const TextStyle(
                color: AppPalette.accent,
                fontWeight: FontWeight.w600,
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    ),
  );
}
