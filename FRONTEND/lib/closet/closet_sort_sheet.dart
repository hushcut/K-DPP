part of '../closet_screen.dart';

/// 정렬 기준 선택 시트와 각 옵션의 시각 표현을 담당합니다.
extension _ClosetSortSheet on _ClosetScreenState {
  /// 정렬 기준 선택 시트를 열고 선택 결과를 화면 상태에 반영합니다.
  Future<void> _showSortBottomSheet() async {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final sheetColor = isDark ? const Color(0xFF121212) : Colors.white;
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF8C8C8C);

    final selected = await showModalBottomSheet<ClosetSortOption>(
      context: context,
      showDragHandle: true,
      backgroundColor: sheetColor,
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
                  '정렬',
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    color: primaryText,
                  ),
                ),
                const SizedBox(height: 20),
                _buildSortOptionTile(
                  label: '친환경 순',
                  value: ClosetSortOption.eco,
                  primaryText: primaryText,
                  secondaryText: secondaryText,
                ),
                _buildSortOptionTile(
                  label: '건강도 순',
                  value: ClosetSortOption.health,
                  primaryText: primaryText,
                  secondaryText: secondaryText,
                ),
                _buildSortOptionTile(
                  label: '최신 등록 순',
                  value: ClosetSortOption.latest,
                  primaryText: primaryText,
                  secondaryText: secondaryText,
                ),
                _buildSortOptionTile(
                  label: '내설정순',
                  value: ClosetSortOption.custom,
                  primaryText: primaryText,
                  secondaryText: secondaryText,
                ),
              ],
            ),
          ),
        );
      },
    );

    if (selected == null) return;

    _updateState(() {
      _sortOption = selected;
      if (selected != ClosetSortOption.custom) {
        _reorderMode = false;
      }
    });
  }

  /// 정렬 시트의 한 옵션과 현재 선택 상태를 표시합니다.
  Widget _buildSortOptionTile({
    required String label,
    required ClosetSortOption value,
    required Color primaryText,
    required Color secondaryText,
  }) {
    final isSelected = _sortOption == value;

    return InkWell(
      onTap: () => Navigator.pop(context, value),
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: TextStyle(
                  fontSize: 18,
                  color: isSelected ? const Color(0xFF4A4EFE) : primaryText,
                  fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                ),
              ),
            ),
            Icon(
              isSelected ? Icons.check : Icons.radio_button_unchecked,
              color: isSelected ? const Color(0xFF4A4EFE) : secondaryText,
            ),
          ],
        ),
      ),
    );
  }
}
