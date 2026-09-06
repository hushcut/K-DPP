// 등록 의류의 검색·정렬·다중 삭제·사용자 지정 순서를 제공하는 옷장 화면입니다.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'closet_provider.dart';
import 'models/closet_sort_option.dart';
import 'models/clothes.dart';
import 'theme/app_palette.dart';

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
  });

  final ValueChanged<Clothes> onOpenReport;
  final VoidCallback? onStartScan;

  /// 옷장 탭이 실제로 보이는 상태인지 나타냅니다.
  /// 숨겨진 상태에서는 뒤로가기 처리에 관여하지 않습니다.
  final bool isActive;

  @override
  State<ClosetScreen> createState() => _ClosetScreenState();
}

/// 화면 상태만 소유하고 실제 동작과 렌더링은 역할별 part 파일에 위임합니다.
class _ClosetScreenState extends State<ClosetScreen> {
  static const double _bottomNavigationOverlapPadding = 26;

  // 다중 선택과 순서 변경은 충돌하지 않도록 서로 배타적으로 관리합니다.
  bool _reorderMode = false;
  final Set<Clothes> _selectedItems = {};

  /// 선택 모드 여부는 선택 집합에서 파생해 별도 동기화가 필요 없게 합니다.
  bool get _selectionMode => _selectedItems.isNotEmpty;
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

  // 선택·순서 변경 모드에서는 시스템 뒤로가기가 앱을 닫는 대신 모드를 끝냅니다.
  // 선택 집합 정리는 canPop 계산보다 먼저 수행해 상태가 어긋나지 않게 합니다.
  @override
  Widget build(BuildContext context) {
    _syncSelectionWithItems(context.watch<ClosetProvider>().items);

    return PopScope(
      canPop: !widget.isActive || (!_selectionMode && !_reorderMode),
      onPopInvokedWithResult: (didPop, _) {
        if (didPop || !widget.isActive) return;

        if (_selectionMode) {
          _exitSelectionMode();
        } else if (_reorderMode) {
          _toggleReorderMode();
        }
      },
      child: _buildClosetBody(context),
    );
  }
}
