// 등록 의류의 검색·정렬·다중 삭제·사용자 지정 순서를 제공하는 옷장 화면입니다.
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'closet_provider.dart';
import 'models/closet_sort_option.dart';
import 'models/clothes.dart';
import 'navigation_bar_opacity_provider.dart';
import 'theme/app_palette.dart';
import 'utils/material_name.dart';
import 'widgets/app_banner.dart';
import 'widgets/bottom_navigation_metrics.dart';
import 'widgets/frosted_surface.dart';
import 'widgets/reorder_bump_haptics.dart';

part 'closet/closet_actions.dart';
part 'closet/closet_body.dart';
part 'closet/closet_list_views.dart';
part 'closet/closet_sort_sheet.dart';

/// 의류를 목록으로 보여 주고 선택한 항목의 상세 리포트를 여는 화면입니다.
class ClosetScreen extends StatefulWidget {
  const ClosetScreen({
    super.key,
    required this.onOpenReport,
    this.onStartScan,
    this.isActive = true,
    this.selectionMode,
  });

  final ValueChanged<Clothes> onOpenReport;
  final VoidCallback? onStartScan;

  /// 옷장 탭이 실제로 보이는 상태인지 나타냅니다.
  /// 숨겨진 상태에서는 뒤로가기 처리에 관여하지 않습니다.
  final bool isActive;

  /// 선택 모드인지 담는 값입니다. 메인 화면이 넘기면 같은 값을 보고 하단 메뉴를 숨깁니다.
  /// 없으면(옷장만 띄운 경우) 화면이 직접 만듭니다. 이 화면만 값을 바꿉니다.
  final ValueNotifier<bool>? selectionMode;

  @override
  State<ClosetScreen> createState() => _ClosetScreenState();
}

/// 화면 상태만 소유하고 실제 동작과 렌더링은 역할별 part 파일에 위임합니다.
class _ClosetScreenState extends State<ClosetScreen> {
  static const double _bottomNavigationOverlapPadding = 26;
  // 헤더 오른쪽 버튼 자리 폭입니다. 제목을 가운데에 두려고 왼쪽도 같은 폭을 비웁니다.
  // 평소 '선택'(TextButton 최소 64) + 정렬(48), 선택 모드 '취소'(64).
  static const double _browseActionsWidth = 112;
  static const double _selectionActionsWidth = 64;

  // 선택 모드는 '선택' 버튼으로 0개부터 들어가므로 선택 집합과 따로 둡니다(2026-10-01).
  // 선택 모드에서는 끌기가 꺼지고, 평소 내 설정 순에서는 ≡ 손잡이로 바로 끕니다.
  ValueNotifier<bool>? _ownSelectionMode;
  final Set<Clothes> _selectedItems = {};
  // 선택한 의류를 지우는 저장이 끝나기 전에는 취소·뒤로로 모드를 끝내지 않습니다.
  bool _deleteInProgress = false;
  // 옷이 모두 사라졌을 때 선택 모드를 끝내는 일을 다음 프레임에 한 번만 예약합니다.
  bool _emptyExitScheduled = false;
  // 옷장 위에 닿아 있는 손가락 수입니다. 모두 떨어지면 끌기 틱 추적을 멈춥니다.
  int _pointersDown = 0;
  // 순서 바꾸기 중 끌고 있는 카드가 다른 카드를 밀어낼 때마다 가벼운 틱을 줍니다.
  final ReorderBumpTracker _reorderBumps = ReorderBumpTracker();

  ValueNotifier<bool> get _selectionModeNotifier =>
      widget.selectionMode ??
      (_ownSelectionMode ??= ValueNotifier<bool>(false));

  bool get _selectionMode => _selectionModeNotifier.value;
  final TextEditingController _searchController = TextEditingController();
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    _searchController.addListener(_handleSearchChanged);
  }

  /// 정렬 기준은 Provider가 단일 출처입니다.
  ///
  /// 화면이 사본을 들고 있으면 저장 실패로 Provider만 되돌아갔을 때 둘이 어긋나고,
  /// 그 어긋남이 화면 재생성(스캔 저장 후 /main 교체, 재로그인 등) 시점에
  /// 아무 안내 없이 드러납니다. 이 화면은 이미 Provider를 구독하므로
  /// 값이 바뀌면 그대로 다시 그려집니다.
  ClosetSortOption get _sortOption =>
      context.read<ClosetProvider>().closetSortOption;

  @override
  void dispose() {
    _reorderBumps.stop();
    _ownSelectionMode?.dispose();
    _searchController.removeListener(_handleSearchChanged);
    _searchController.dispose();
    super.dispose();
  }

  /// part 확장이 보호 멤버인 setState를 직접 호출하지 않도록 중계합니다.
  void _updateState(VoidCallback callback) => setState(callback);

  /// 다른 화면에서 항목이 삭제·교체돼도 선택 집합이 어긋나지 않게 맞춥니다.
  /// 인스턴스가 바뀐 항목은 서버 저장 ID로 다시 찾아 새 인스턴스로 교체합니다.
  void _syncSelectionWithItems(List<Clothes> items) {
    if (_selectedItems.isEmpty) return;

    final replacement = <Clothes>[];

    for (final selected in _selectedItems) {
      for (final item in items) {
        final isSameItem =
            identical(item, selected) ||
            (selected.savedResultId != null &&
                item.savedResultId == selected.savedResultId);

        if (isSameItem) {
          replacement.add(item);
          break;
        }
      }
    }

    _selectedItems
      ..clear()
      ..addAll(replacement);
  }

  /// 선택 중 옷이 모두 사라지면(다른 화면에서 지움 등) 다음 프레임에 선택 모드를 끝냅니다.
  /// 빌드 중에는 메인 화면과 함께 보는 값을 바꿀 수 없어 미룹니다. 삭제 저장 중에는 목록이 먼저
  /// 비었다가 실패하면 되돌아오므로 끝내지 않습니다.
  void _exitSelectionWhenClosetEmpty(List<Clothes> items) {
    if (!_selectionMode || items.isNotEmpty || _deleteInProgress) return;
    if (_emptyExitScheduled) return;

    _emptyExitScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _emptyExitScheduled = false;
      if (!mounted || _deleteInProgress) return;
      if (context.read<ClosetProvider>().items.isNotEmpty) return;

      _setSelectionMode(false);
    });
  }

  // 선택 모드에서는 시스템 뒤로가기가 앱을 닫는 대신 모드를 끝냅니다(삭제 저장 중에는 그대로).
  // 선택 집합 정리는 canPop 계산보다 먼저 수행해 상태가 어긋나지 않게 합니다.
  @override
  Widget build(BuildContext context) {
    final items = context.watch<ClosetProvider>().items;
    _syncSelectionWithItems(items);
    _exitSelectionWhenClosetEmpty(items);

    return PopScope(
      canPop: !widget.isActive || !_selectionMode,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop || !widget.isActive || _deleteInProgress) return;

        _setSelectionMode(false);
      },
      child: _buildClosetBody(context),
    );
  }
}
