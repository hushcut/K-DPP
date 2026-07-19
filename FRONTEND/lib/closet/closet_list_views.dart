part of '../closet_screen.dart';

/// 빈 상태·일반 목록·재정렬 목록과 각 의류 항목의 표현을 담당합니다.
extension _ClosetListViews on _ClosetScreenState {
  /// 하단 내비게이션과 기기 안전 영역이 목록을 가리지 않도록 여백을 둡니다.
  EdgeInsets _listPadding(BuildContext context) {
    return EdgeInsets.fromLTRB(
      16,
      16,
      16,
      _ClosetScreenState._bottomNavigationOverlapPadding +
          MediaQuery.paddingOf(context).bottom,
    );
  }

  /// 목록이 비었을 때 검색 초기화 또는 스캔 시작 동작을 안내합니다.
  Widget _buildEmptyListState({
    required String message,
    required _ClosetPalette palette,
  }) {
    final isSearching = _searchQuery.isNotEmpty;
    final action = isSearching ? _searchController.clear : widget.onStartScan;

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isSearching ? Icons.search_off_rounded : Icons.checkroom_outlined,
              color: palette.secondaryText,
              size: 34,
            ),
            const SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: palette.primaryText,
                fontSize: 15,
                fontWeight: FontWeight.w700,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              isSearching
                  ? '검색어를 지우고 전체 옷장을 다시 확인해 보세요.'
                  : '케어 라벨을 스캔하면 소재와 유해성 정보를 옷장에 저장할 수 있어요.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: palette.secondaryText,
                fontSize: 13,
                height: 1.5,
              ),
            ),
            if (action != null) ...[
              const SizedBox(height: 18),
              SizedBox(
                height: 44,
                child: ElevatedButton.icon(
                  onPressed: action,
                  icon: Icon(
                    isSearching
                        ? Icons.close_rounded
                        : Icons.camera_alt_outlined,
                    size: 18,
                  ),
                  label: Text(isSearching ? '검색어 지우기' : '스캔하러 가기'),
                  style: ElevatedButton.styleFrom(
                    elevation: 0,
                    backgroundColor: const Color(0xFF4A4EFE),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(horizontal: 18),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  /// 사용자 지정 순서를 드래그로 바꾸는 목록입니다.
  Widget _buildReorderableClothesList(
    BuildContext context,
    List<Clothes> clothes,
    List<Clothes> originalOrder, {
    required String emptyMessage,
    required _ClosetPalette palette,
  }) {
    if (clothes.isEmpty) {
      return _buildEmptyListState(
        message: emptyMessage,
        palette: palette,
      );
    }

    return ReorderableListView.builder(
      padding: _listPadding(context),
      itemCount: clothes.length,
      onReorder: (oldIndex, newIndex) async {
        await _handleReorder(
          displayedItems: clothes,
          originalOrder: originalOrder,
          oldIndex: oldIndex,
          newIndex: newIndex,
        );
      },
      itemBuilder: (context, index) {
        final item = clothes[index];

        return Padding(
          key: ValueKey(item),
          padding: const EdgeInsets.only(bottom: 12.0),
          child: _buildClosetItem(
            context,
            item: item,
            title: item.title,
            category: item.category,
            status: item.health > 20
                ? '건강 상태: ${item.health}%'
                : '수명 만료 (배출 권장)',
            statusColor: item.health > 20 ? Colors.green : Colors.redAccent,
            statusIcon: item.health > 20
                ? Icons.sentiment_satisfied_alt
                : Icons.warning_amber_rounded,
            isWarning: item.health <= 20,
            showDragHandle: true,
            disableTap: true,
            palette: palette,
          ),
        );
      },
    );
  }

  /// 일반 탐색과 다중 선택에 사용하는 의류 목록입니다.
  Widget _buildClothesList(
    BuildContext context,
    List<Clothes> clothes, {
    required String emptyMessage,
    required _ClosetPalette palette,
  }) {
    if (clothes.isEmpty) {
      return _buildEmptyListState(
        message: emptyMessage,
        palette: palette,
      );
    }

    return ListView.builder(
      padding: _listPadding(context),
      itemCount: clothes.length,
      itemBuilder: (context, index) {
        final item = clothes[index];

        return Padding(
          padding: const EdgeInsets.only(bottom: 12.0),
          child: _buildClosetItem(
            context,
            item: item,
            title: item.title,
            category: item.category,
            status: item.health > 20
                ? '건강 상태: ${item.health}%'
                : '수명 만료 (배출 권장)',
            statusColor: item.health > 20 ? Colors.green : Colors.redAccent,
            statusIcon: item.health > 20
                ? Icons.sentiment_satisfied_alt
                : Icons.warning_amber_rounded,
            isWarning: item.health <= 20,
            palette: palette,
          ),
        );
      },
    );
  }

  /// 의류의 분류·건강 상태와 선택·경고·재정렬 상태를 한 행에 표시합니다.
  Widget _buildClosetItem(
    BuildContext context, {
    required Clothes item,
    required String title,
    required String category,
    required String status,
    required Color statusColor,
    required IconData statusIcon,
    required _ClosetPalette palette,
    bool isWarning = false,
    bool showDragHandle = false,
    bool disableTap = false,
  }) {
    final isSelected = _selectedItems.contains(item);

    return Semantics(
      selected: isSelected,
      child: Container(
        decoration: BoxDecoration(
          color: isSelected
              ? palette.selectedBgColor
              : (isWarning ? palette.warningBgColor : palette.cardColor),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isSelected
                ? const Color(0xFF4A4EFE)
                : (isWarning
                      ? Colors.redAccent.shade200
                      : palette.borderColor),
            width: isSelected ? 2 : (isWarning ? 2 : 1),
          ),
          boxShadow: [
            BoxShadow(
              color: palette.shadowColor,
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: ListTile(
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 16,
            vertical: 8,
          ),
          leading: Container(
            width: 60,
            height: 60,
            decoration: BoxDecoration(
              color: isSelected
                  ? (palette.isDark
                        ? const Color(0xFF1C1C1E)
                        : Colors.white)
                  : (isWarning
                        ? (palette.isDark
                              ? const Color(0xFF1C1C1E)
                              : Colors.white)
                        : palette.leadingBgColor),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              Icons.checkroom,
              color: isSelected
                  ? const Color(0xFF4A4EFE)
                  : (isWarning
                        ? Colors.redAccent
                        : palette.secondaryText),
              size: 30,
            ),
          ),
          title: Text(
            title,
            maxLines: 2,
            style: TextStyle(
              fontWeight: FontWeight.bold,
              fontSize: 16,
              color: palette.primaryText,
            ),
          ),
          subtitle: Padding(
            padding: const EdgeInsets.only(top: 8.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  category,
                  style: TextStyle(
                    color: palette.secondaryText,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Icon(statusIcon, color: statusColor, size: 16),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        status,
                        maxLines: 2,
                        style: TextStyle(
                          color: statusColor,
                          fontWeight: isWarning
                              ? FontWeight.bold
                              : FontWeight.normal,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          trailing: showDragHandle
              ? Icon(Icons.drag_handle, color: palette.secondaryText)
              : (_selectionMode
                    ? Icon(
                        isSelected
                            ? Icons.check_circle
                            : Icons.radio_button_unchecked,
                        color: isSelected
                            ? const Color(0xFF4A4EFE)
                            : palette.secondaryText,
                      )
                    : Icon(
                        Icons.chevron_right,
                        color: palette.secondaryText,
                      )),
          onTap: disableTap
              ? null
              : () {
                  if (_selectionMode) {
                    _toggleSelection(item);
                    return;
                  }

                  context.read<ClosetProvider>().selectClothes(item);
                  widget.onOpenReport(item);
                },
          onLongPress: disableTap
              ? null
              : () {
                  if (_selectionMode) {
                    _toggleSelection(item);
                    return;
                  }

                  _enterSelectionMode(item);
                },
        ),
      ),
    );
  }
}
