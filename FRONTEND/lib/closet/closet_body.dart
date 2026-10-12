part of '../closet_screen.dart';

/// 옷장 상단 상태와 탭별 목록을 조합해 화면 본문을 만듭니다.
extension _ClosetBody on _ClosetScreenState {
  Widget _buildClosetBody(BuildContext context) {
    // Provider 원본에서 검색·정렬된 탭별 표시 목록을 매 빌드마다 계산합니다.
    final clothesList = context.watch<ClosetProvider>().items;
    final originalOrder = clothesList.toList();
    final palette = _ClosetPalette.from(context);

    // 전체를 한 번만 정렬한 뒤 분류로 나눠 빌드당 정렬 비용을 1회로 줄입니다.
    final sortedItems = _sortClothes(
      List<Clothes>.from(clothesList),
      originalOrder,
    );
    final allItems = _filterClothes(sortedItems);
    final topItems = _filterClothes(
      sortedItems.where((item) => item.category == '상의').toList(),
    );
    final bottomItems = _filterClothes(
      sortedItems.where((item) => item.category == '하의').toList(),
    );

    // 끄는 도중 취소·두 번째 손가락·목록 교체로 끝나면 onReorderEnd 가 불리지 않아 틱 추적이
    // 남습니다. 옷장 위의 손가락이 모두 떨어지면 함께 멈춥니다(정상으로 끝날 때도 같은 때라 해가 없음).
    return Listener(
      onPointerDown: (_) => _pointersDown++,
      onPointerUp: (_) => _releasePointer(),
      onPointerCancel: (_) => _releasePointer(),
      child: Stack(
        children: [
          DefaultTabController(
            length: 3,
            child: Column(
              children: [
                _buildHeader(palette, hasClothes: clothesList.isNotEmpty),
                _buildCategoryTabBar(palette),
                Expanded(
                  child: TabBarView(
                    children: [
                      _buildCategoryTab(
                        context: context,
                        items: allItems,
                        originalOrder: originalOrder,
                        emptyMessage: '옷장에 등록된 의류가 없습니다.',
                        palette: palette,
                        storageKey: const PageStorageKey('closet-list-all'),
                      ),
                      _buildCategoryTab(
                        context: context,
                        items: topItems,
                        originalOrder: originalOrder,
                        emptyMessage: '상의 의류가 없습니다.',
                        palette: palette,
                        storageKey: const PageStorageKey('closet-list-top'),
                      ),
                      _buildCategoryTab(
                        context: context,
                        items: bottomItems,
                        originalOrder: originalOrder,
                        emptyMessage: '하의 의류가 없습니다.',
                        palette: palette,
                        storageKey: const PageStorageKey('closet-list-bottom'),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (_selectionMode) _buildTrashButton(context),
        ],
      ),
    );
  }

  void _releasePointer() {
    if (_pointersDown > 0) _pointersDown--;
    if (_pointersDown == 0) _reorderBumps.stop();
  }

  /// 제목·정렬 안내·검색창을 담은 위쪽 헤더입니다.
  ///
  /// 선택 모드에서는 틀을 그대로 두고 윗줄만 바꿉니다('내 옷장' → 'n개 선택됨', '선택'·정렬 → '취소').
  /// 헤더를 통째로 바꾸면 목록이 위아래로 튀고, 검색 중이라 일부만 보이는 이유가 사라집니다.
  Widget _buildHeader(_ClosetPalette palette, {required bool hasClothes}) {
    final selecting = _selectionMode;

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
      child: Column(
        children: [
          _buildHeaderTitleRow(
            palette,
            selecting: selecting,
            hasClothes: hasClothes,
          ),
          const SizedBox(height: 10),
          Text(
            '현재 정렬: $_sortLabel',
            style: TextStyle(color: palette.secondaryText, fontSize: 13),
          ),
          const SizedBox(height: 6),
          // 내 설정 순의 ≡ 손잡이는 따로 안내하지 않습니다(2026-10-01 사용자 결정).
          Text(
            _sortOption == ClosetSortOption.custom
                ? '내 설정 순으로 정렬되어 있어요.'
                : '원하는 방식으로 옷장을 정리해 보세요.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: palette.secondaryText,
              fontSize: 12,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 14),
          _buildSearchField(palette, enabled: !selecting),
        ],
      ),
    );
  }

  /// 가운데 제목과 오른쪽 버튼 줄입니다.
  ///
  /// 겹쳐 쌓으면(Stack) 작은 화면·큰 글자에서 제목과 버튼이 겹치므로, 오른쪽 버튼 자리만큼
  /// 왼쪽도 비워 제목을 가운데에 두고, 남는 폭이 모자라면 제목을 줄입니다.
  Widget _buildHeaderTitleRow(
    _ClosetPalette palette, {
    required bool selecting,
    required bool hasClothes,
  }) {
    final actionsWidth = selecting
        ? _ClosetScreenState._selectionActionsWidth
        : _ClosetScreenState._browseActionsWidth;

    final actions = selecting
        ? [
            TextButton(
              onPressed: _deleteInProgress
                  ? null
                  : () => _setSelectionMode(false),
              child: const Text('취소'),
            ),
          ]
        : [
            // 정렬과 상관없이 고르고 지우는 모드입니다. 옷이 없으면 고를 것이 없어 누를 수 없습니다.
            TextButton(
              onPressed: hasClothes ? () => _setSelectionMode(true) : null,
              child: const Text('선택'),
            ),
            IconButton(
              onPressed: _showSortBottomSheet,
              tooltip: '옷장 정렬',
              icon: const Icon(Icons.sort, color: AppPalette.accent),
            ),
          ];

    return Row(
      children: [
        SizedBox(width: actionsWidth),
        Expanded(
          child: Center(
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(
                selecting ? '${_selectedItems.length}개 선택됨' : '내 옷장',
                maxLines: 1,
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                  color: palette.primaryText,
                ),
              ),
            ),
          ),
        ),
        ConstrainedBox(
          constraints: BoxConstraints(minWidth: actionsWidth),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.end,
            children: actions,
          ),
        ),
      ],
    );
  }

  /// 선택 모드에서 숨은 하단 메뉴 막대 자리 왼쪽에 띄우는 동그란 휴지통입니다.
  ///
  /// 한 손으로 닿는 아래쪽에 두고, 0개일 때도 흐리게 떠 있어 위치를 미리 익히게 합니다
  /// (참고: Apple Music 플레이리스트 편집, 2026-10-01 DECISIONS 75).
  Widget _buildTrashButton(BuildContext context) {
    const size = 56.0;
    final appPalette = AppPalette.of(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    // 하단 메뉴와 같은 반투명도를 씁니다. 옷장만 띄운 경우(메뉴 없음)엔 불투명하게 칠합니다.
    final opacity =
        context.watch<NavigationBarOpacityProvider?>()?.opacity ?? 1.0;
    final canDelete = _selectedItems.isNotEmpty && !_deleteInProgress;

    // 본문의 아래 안쪽 여백(padding.bottom)은 하단 메뉴 자리 높이입니다(Scaffold.extendBody).
    // 그 자리 안 막대의 세로 가운데에 맞추고, 메뉴가 없으면 아래에서 16 띄웁니다.
    // 본문의 viewPadding.bottom 은 메뉴가 있으면 0 이라 기준이 될 수 없습니다.
    final mediaPadding = MediaQuery.paddingOf(context);
    final bottom = math.max(
      16.0,
      mediaPadding.bottom -
          BottomNavigationMetrics.boxHeight +
          (BottomNavigationMetrics.barHeight - size) / 2,
    );

    return Positioned(
      left: mediaPadding.left + BottomNavigationMetrics.horizontalMargin,
      bottom: bottom,
      // 하단 메뉴가 내려가는 동안 화면 아래에서 올라옵니다.
      child: TweenAnimationBuilder<double>(
        tween: Tween<double>(begin: 0, end: 1),
        duration: const Duration(milliseconds: 260),
        curve: Curves.easeOutCubic,
        builder: (context, t, child) => Transform.translate(
          offset: Offset(0, (1 - t) * (bottom + size)),
          child: child,
        ),
        child: SizedBox.square(
          dimension: size,
          child: FrostedSurface(
            opacity: opacity,
            color: appPalette.card,
            borderRadius: BorderRadius.circular(size / 2),
            border: Border.all(color: appPalette.border),
            boxShadow: [
              BoxShadow(
                color: isDark
                    ? Colors.black.withValues(alpha: 0.30)
                    : Colors.black.withValues(alpha: 0.10),
                blurRadius: 22,
                offset: const Offset(0, 8),
              ),
            ],
            child: IconButton(
              onPressed: canDelete ? _deleteSelectedItems : null,
              color: Colors.redAccent,
              // 이름은 tooltip 대신 아이콘 낭독 이름으로 줍니다. iOS VoiceOver 는 tooltip 만 있고 누를 수
              // 없는 칸을 건너뛰어, 아무것도 고르지 않았을 때 휴지통이 사라집니다(2026-10-02).
              // 확인창 제목('선택한 의류 삭제')과 겹치지 않는 이름입니다.
              icon: const Icon(
                Icons.delete_outline,
                size: 26,
                semanticLabel: '선택한 의류 지우기',
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// 검색어 입력과 초기화 버튼을 제공하는 검색창입니다.
  /// 선택 모드에서는 보이기만 하고 입력·지우기는 막습니다(일부만 보이는 이유를 남겨 둠).
  Widget _buildSearchField(_ClosetPalette palette, {required bool enabled}) {
    return TextField(
      controller: _searchController,
      enabled: enabled,
      style: TextStyle(color: palette.primaryText, fontSize: 14),
      textInputAction: TextInputAction.search,
      decoration: InputDecoration(
        hintText: '옷 이름, 소재 검색',
        hintStyle: TextStyle(color: palette.secondaryText, fontSize: 14),
        prefixIcon: Icon(
          Icons.search,
          color: palette.secondaryText,
          size: 21,
        ),
        suffixIcon: _searchQuery.isEmpty
            ? null
            : IconButton(
                onPressed: enabled ? _searchController.clear : null,
                tooltip: '검색어 지우기',
                icon: Icon(
                  Icons.close,
                  color: palette.secondaryText,
                  size: 20,
                ),
              ),
        filled: true,
        fillColor: palette.cardColor,
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 14,
          vertical: 14,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: palette.borderColor),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: palette.borderColor),
        ),
        disabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: palette.borderColor),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: AppPalette.accent, width: 1.4),
        ),
      ),
    );
  }

  /// 전체·상의·하의 목록 사이를 전환하는 탭입니다.
  Widget _buildCategoryTabBar(_ClosetPalette palette) {
    return TabBar(
      labelColor: AppPalette.accent,
      unselectedLabelColor: palette.secondaryText,
      indicatorColor: AppPalette.accent,
      indicatorWeight: 3,
      tabs: const [
        Tab(text: '전체'),
        Tab(text: '상의'),
        Tab(text: '하의'),
      ],
    );
  }

  /// 내 설정 순 평소에는 ≡ 로 끄는 목록, 그 밖(다른 정렬·선택 모드)에는 일반 목록을 씁니다.
  ///
  /// 두 목록이 같은 [storageKey] 를 써서 탭마다 스크롤 위치를 기억합니다. 선택 모드를 오가며
  /// 목록 종류가 바뀌거나 탭을 옮겨 목록이 다시 만들어져도 보던 자리에서 이어집니다.
  Widget _buildCategoryTab({
    required BuildContext context,
    required List<Clothes> items,
    required List<Clothes> originalOrder,
    required String emptyMessage,
    required _ClosetPalette palette,
    required Key storageKey,
  }) {
    final resolvedEmptyMessage = _emptyMessage(emptyMessage);

    if (_sortOption == ClosetSortOption.custom && !_selectionMode) {
      return _buildReorderableClothesList(
        context,
        items,
        originalOrder,
        emptyMessage: resolvedEmptyMessage,
        palette: palette,
        storageKey: storageKey,
      );
    }

    return _buildClothesList(
      context,
      items,
      emptyMessage: resolvedEmptyMessage,
      palette: palette,
      storageKey: storageKey,
    );
  }
}

/// 밝은 테마와 어두운 테마에서 목록이 함께 사용하는 색상 묶음입니다.
class _ClosetPalette {
  const _ClosetPalette({
    required this.primaryText,
    required this.secondaryText,
    required this.cardColor,
    required this.borderColor,
    required this.selectedBgColor,
    required this.warningBgColor,
    required this.leadingBgColor,
    required this.shadowColor,
    required this.isDark,
  });

  factory _ClosetPalette.from(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return _ClosetPalette(
      primaryText: isDark ? Colors.white : const Color(0xFF1A1A1A),
      secondaryText: isDark
          ? const Color(0xFFD1D1D6)
          : const Color(0xFF5F6368),
      cardColor: isDark ? const Color(0xFF1C1C1E) : Colors.white,
      borderColor: isDark
          ? const Color(0xFF2C2C2E)
          : Colors.grey.shade200,
      selectedBgColor: isDark
          ? const Color(0xFF232A45)
          : const Color(0xFFEEF1FF),
      warningBgColor: isDark
          ? const Color(0xFF2A1E1E)
          : Colors.red.shade50,
      leadingBgColor: isDark
          ? const Color(0xFF2A2A2E)
          : Colors.grey.shade100,
      shadowColor: isDark
          ? Colors.black.withValues(alpha: 0.16)
          : Colors.black.withValues(alpha: 0.03),
      isDark: isDark,
    );
  }

  final Color primaryText;
  final Color secondaryText;
  final Color cardColor;
  final Color borderColor;
  final Color selectedBgColor;
  final Color warningBgColor;
  final Color leadingBgColor;
  final Color shadowColor;
  final bool isDark;
}
