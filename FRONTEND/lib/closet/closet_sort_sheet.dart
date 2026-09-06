part of '../closet_screen.dart';

/// 정렬 기준 선택 시트와 각 옵션의 시각 표현을 담당합니다.
extension _ClosetSortSheet on _ClosetScreenState {
  /// 정렬 기준 선택 시트를 열고 선택 결과를 화면 상태에 반영합니다.
  Future<void> _showSortBottomSheet() async {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);
    final primaryText = palette.textPrimary;
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
          // 작은 화면이나 큰 글자 설정에서 옵션이 잘리지 않도록 스크롤을 허용합니다.
          child: SingleChildScrollView(
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
                  label: '내 설정 순',
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

    // 시트가 닫히는 사이 화면이 사라졌을 수 있으므로 상태 갱신 전에 확인합니다.
    if (selected == null || !mounted) return;

    final provider = context.read<ClosetProvider>();

    _updateState(() {
      _sortOption = selected;
      if (selected != ClosetSortOption.custom) {
        _reorderMode = false;
      }
    });

    // 저장 실패는 화면을 되돌리지 않고 안내만 합니다. 정렬은 다시 고르면 되고,
    // 사용자가 방금 선택한 화면을 되돌리는 편이 더 혼란스럽기 때문입니다.
    try {
      await provider.setClosetSortOption(selected);
    } catch (_) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('정렬 방식을 저장하지 못했어요. 앱을 다시 열면 이전 기준으로 돌아갑니다.')),
      );
    }
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
                  color: isSelected ? AppPalette.accent : primaryText,
                  fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                ),
              ),
            ),
            Icon(
              isSelected ? Icons.check : Icons.radio_button_unchecked,
              color: isSelected ? AppPalette.accent : secondaryText,
            ),
          ],
        ),
      ),
    );
  }
}
