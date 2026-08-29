// 홈·스캔·옷장 탭과 상세 리포트 전환을 한 화면에서 관리하는 앱의 메인 셸입니다.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'closet_provider.dart';
import 'closet_screen.dart';
import 'home_screen.dart';
import 'models/clothes.dart';
import 'models/main_screen_arguments.dart';
import 'report_screen.dart';
import 'scan_screen.dart';
import 'theme/app_palette.dart';
import 'widgets/kdpp_logo_mark.dart';

/// 하단 내비게이션의 선택 상태와 리포트 오버레이 표시 상태를 관리합니다.
class MainScreen extends StatefulWidget {
  const MainScreen({super.key, this.initialArguments});

  final MainScreenArguments? initialArguments;

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen>
    with SingleTickerProviderStateMixin {
  static const int _tabCount = 3;
  static const Duration _transitionDuration = Duration(milliseconds: 260);

  int _selectedIndex = 0;
  bool _didReadInitialArgs = false;
  bool _isShowingReport = false;
  // 설정 같은 라우트가 위에 열리는 동안 스캔 카메라를 멈추기 위한 표시입니다.
  bool _isCoveredByRoute = false;

  // 탭을 바꿀 때마다 새 화면이 부드럽게 나타나도록 재생하는 전환 애니메이션입니다.
  late final AnimationController _tabTransitionController;
  late final Animation<double> _tabTransition;
  // 이동 방향에 맞춰 새 화면이 들어오는 쪽을 정합니다.
  double _tabSlideDirection = 1;

  @override
  void initState() {
    super.initState();
    _tabTransitionController = AnimationController(
      vsync: this,
      duration: _transitionDuration,
      value: 1,
    );
    _tabTransition = CurvedAnimation(
      parent: _tabTransitionController,
      curve: Curves.easeOutCubic,
    );
  }

  @override
  void dispose() {
    _tabTransitionController.dispose();
    super.dispose();
  }

  // 탭을 바꾸면 열려 있던 상세 리포트도 함께 닫습니다.
  void _selectTab(int index) {
    if (index < 0 || index >= _tabCount) return;

    final isSameView = index == _selectedIndex && !_isShowingReport;
    // 오른쪽 탭으로 가면 오른쪽에서, 왼쪽 탭으로 가면 왼쪽에서 들어옵니다.
    final direction = index >= _selectedIndex ? 1.0 : -1.0;

    setState(() {
      _selectedIndex = index;
      _isShowingReport = false;
      _tabSlideDirection = direction;
    });

    // 같은 탭을 다시 누른 경우에는 굳이 다시 재생하지 않습니다.
    if (!isSameView) {
      _tabTransitionController.forward(from: 0);
    }
  }

  /// 촬영에 집중할 수 있도록 하단 내비게이션을 감추는 스캔 화면 상태입니다.
  bool get _isScanTabActive => _selectedIndex == 1 && !_isShowingReport;

  // 선택 의류를 Provider에 기록한 뒤 탭 위에 상세 리포트를 표시합니다.
  void _openReport(Clothes item) {
    // 탭 트리가 유지되므로, 검색창 등에 남은 포커스와 키보드를 먼저 정리합니다.
    FocusManager.instance.primaryFocus?.unfocus();
    context.read<ClosetProvider>().selectClothes(item);

    setState(() {
      _isShowingReport = true;
    });
  }

  void _closeReport() {
    setState(() {
      _isShowingReport = false;
    });
  }

  void _handleReportDeleted() {
    setState(() {
      _selectedIndex = 2;
      _isShowingReport = false;
    });
  }

  int _normalizeInitialIndex(int index) {
    if (index == 3) return 2;

    if (index >= 0 && index < _tabCount) {
      return index;
    }

    return 0;
  }

  /// 외부 경로에서 전달된 초기 탭과 리포트 표시 요청을 한 번만 적용합니다.
  void _applyInitialArguments(Object? args) {
    if (args is MainScreenArguments) {
      _selectedIndex = _normalizeInitialIndex(args.initialIndex);
      _isShowingReport =
          args.showReport &&
          context.read<ClosetProvider>().currentReportItem != null;
      return;
    }

    _selectedIndex = _normalizeInitialIndex(args is int ? args : 0);
  }

  // 설정 화면이 닫힐 때까지 카메라가 꺼지도록 열림 상태를 추적합니다.
  Future<void> _openSettings() async {
    // 빠른 연속 탭으로 설정 화면이 두 번 쌓이지 않게 합니다.
    if (_isCoveredByRoute) return;

    setState(() {
      _isCoveredByRoute = true;
    });

    await Navigator.pushNamed(context, '/settings');

    if (!mounted) return;

    setState(() {
      _isCoveredByRoute = false;
    });
  }

  List<Widget> _buildTabScreens() {
    return [
      HomeScreen(
        onStartScan: () => _selectTab(1),
        onOpenReport: _openReport,
        onOpenCloset: () => _selectTab(2),
      ),
      ScanScreen(
        isActive:
            _selectedIndex == 1 && !_isShowingReport && !_isCoveredByRoute,
      ),
      ClosetScreen(
        isActive:
            _selectedIndex == 2 && !_isShowingReport && !_isCoveredByRoute,
        onOpenReport: _openReport,
        onStartScan: () => _selectTab(1),
      ),
    ];
  }

  // 리포트가 열려도 탭 트리는 Offstage로 유지해 작성 중 상태를 보존하고,
  // 리포트 층만 AnimatedSwitcher로 위에 얹거나 걷어냅니다.
  Widget _buildBody() {
    return Stack(
      fit: StackFit.expand,
      children: [
        Offstage(
          offstage: _isShowingReport,
          child: TickerMode(
            enabled: !_isShowingReport,
            // 탭을 유지한 채(작성 중인 내용 보존) 화면만 부드럽게 나타나게 합니다.
            child: FadeTransition(
              opacity: _tabTransition,
              child: SlideTransition(
                position: Tween<Offset>(
                  begin: Offset(0.06 * _tabSlideDirection, 0),
                  end: Offset.zero,
                ).animate(_tabTransition),
                child: IndexedStack(
                  index: _selectedIndex,
                  children: _buildTabScreens(),
                ),
              ),
            ),
          ),
        ),
        AnimatedSwitcher(
          duration: _transitionDuration,
          switchInCurve: Curves.easeOutCubic,
          switchOutCurve: Curves.easeInCubic,
          transitionBuilder: (child, animation) {
            final slideAnimation = Tween<Offset>(
              begin: const Offset(0.04, 0),
              end: Offset.zero,
            ).animate(animation);

            return FadeTransition(
              opacity: animation,
              child: SlideTransition(position: slideAnimation, child: child),
            );
          },
          child: _isShowingReport
              ? ReportScreen(
                  key: const ValueKey('report'),
                  onDeleted: _handleReportDeleted,
                )
              : const SizedBox.shrink(key: ValueKey('report-hidden')),
        ),
      ],
    );
  }

  PreferredSizeWidget _buildAppBar(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final appBarIconColor = isDark ? Colors.white : const Color(0xFF1A1A1A);

    if (_isShowingReport) {
      return AppBar(
        toolbarHeight: 44,
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        leading: IconButton(
          onPressed: _closeReport,
          tooltip: '리포트 닫기',
          icon: Icon(Icons.arrow_back, color: appBarIconColor),
        ),
        title: Text(
          '상세 리포트',
          style: TextStyle(
            color: appBarIconColor,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
      );
    }

    return AppBar(
      toolbarHeight: 56,
      backgroundColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      automaticallyImplyLeading: false,
      centerTitle: true,
      // 스캔 화면에서는 하단 내비게이션이 없으므로 나가는 버튼을 제공합니다.
      leading: _isScanTabActive
          ? IconButton(
              onPressed: () => _selectTab(0),
              tooltip: '스캔 화면 닫기',
              icon: Icon(Icons.arrow_back, color: appBarIconColor),
            )
          : null,
      title: const KdppLogoMark(size: 34, borderRadius: 10),
      actions: [
        IconButton(
          onPressed: _openSettings,
          tooltip: '설정',
          icon: Icon(Icons.settings_outlined, color: appBarIconColor),
        ),
        const SizedBox(width: 8),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_didReadInitialArgs) {
      final args =
          widget.initialArguments ?? ModalRoute.of(context)?.settings.arguments;
      _applyInitialArguments(args);
      _didReadInitialArgs = true;
    }

    final palette = AppPalette.of(context);
    final scaffoldBg = palette.background;

    // '/main'은 스택의 유일한 라우트라서, 리포트가 열려 있거나 스캔 화면일 때
    // 시스템 뒤로가기가 앱을 종료하지 않고 이전 화면으로 돌아가게 합니다.
    return PopScope(
      canPop: !_isShowingReport && !_isScanTabActive,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) return;

        if (_isShowingReport) {
          _closeReport();
          return;
        }

        if (_isScanTabActive) {
          _selectTab(0);
        }
      },
      child: Scaffold(
        backgroundColor: scaffoldBg,
        extendBody: true,
        appBar: _buildAppBar(context),
        body: _buildBody(),
        // 촬영 중에는 하단 내비게이션을 감춰 화면을 넓게 사용하고,
        // 사라지고 나타날 때는 아래로 밀려나듯 부드럽게 전환합니다.
        bottomNavigationBar: AnimatedSize(
          duration: _transitionDuration,
          curve: Curves.easeOutCubic,
          alignment: Alignment.topCenter,
          child: _isScanTabActive
              ? const SizedBox(width: double.infinity)
              : _KDppBottomNavigationBar(
                  selectedIndex: _selectedIndex,
                  onSelect: _selectTab,
                ),
        ),
      ),
    );
  }
}

/// 좌우 탭과 가운데 돌출형 스캔 버튼을 배치하는 전용 하단 내비게이션입니다.
class _KDppBottomNavigationBar extends StatelessWidget {
  const _KDppBottomNavigationBar({
    required this.selectedIndex,
    required this.onSelect,
  });

  final int selectedIndex;
  final ValueChanged<int> onSelect;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);

    final pageBg = palette.background;
    final barColor = palette.card;
    final borderColor = palette.border;
    final shadowColor = isDark
        ? Colors.black.withValues(alpha: 0.30)
        : Colors.black.withValues(alpha: 0.10);

    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 0, 18, 12),
        child: SizedBox(
          height: 94,
          child: Stack(
            clipBehavior: Clip.none,
            alignment: Alignment.bottomCenter,
            children: [
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: Container(
                  height: 70,
                  decoration: BoxDecoration(
                    color: barColor,
                    borderRadius: BorderRadius.circular(26),
                    border: Border.all(color: borderColor),
                    boxShadow: [
                      BoxShadow(
                        color: shadowColor,
                        blurRadius: 22,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: _BottomTabItem(
                          icon: Icons.home_outlined,
                          activeIcon: Icons.home,
                          label: '홈',
                          selected: selectedIndex == 0,
                          onTap: () => onSelect(0),
                        ),
                      ),
                      const SizedBox(width: 88),
                      Expanded(
                        child: _BottomTabItem(
                          icon: Icons.checkroom_outlined,
                          activeIcon: Icons.checkroom,
                          label: '옷장',
                          selected: selectedIndex == 2,
                          onTap: () => onSelect(2),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              Positioned(
                top: 0,
                child: _CenterScanButton(
                  pageBg: pageBg,
                  selected: selectedIndex == 1,
                  onTap: () => onSelect(1),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// 스캔 탭을 강조하는 가운데 원형 카메라 버튼입니다.
class _CenterScanButton extends StatelessWidget {
  const _CenterScanButton({
    required this.pageBg,
    required this.selected,
    required this.onTap,
  });

  final Color pageBg;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    const activeColor = AppPalette.accent;
    final labelColor = selected ? activeColor : palette.textSecondary;

    return Semantics(
      label: '스캔',
      button: true,
      selected: selected,
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: SizedBox(
          width: 88,
          height: 90,
          child: ExcludeSemantics(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 66,
                  height: 66,
                  padding: const EdgeInsets.all(5),
                  decoration: BoxDecoration(
                    color: pageBg,
                    shape: BoxShape.circle,
                  ),
                  child: Container(
                    decoration: BoxDecoration(
                      color: selected ? AppPalette.accentPressed : activeColor,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: activeColor.withValues(alpha: 0.34),
                          blurRadius: 18,
                          offset: const Offset(0, 8),
                        ),
                      ],
                    ),
                    child: const Icon(
                      Icons.camera_alt,
                      color: Colors.white,
                      size: 30,
                    ),
                  ),
                ),
                const SizedBox(height: 1),
                SizedBox(
                  height: 18,
                  child: Center(
                    child: Text(
                      '스캔',
                      style: TextStyle(
                        color: labelColor,
                        fontSize: 12,
                        height: 1.1,
                        fontWeight: selected
                            ? FontWeight.w700
                            : FontWeight.w500,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// 선택 상태에 따라 아이콘·색상을 바꾸는 일반 하단 탭 항목입니다.
class _BottomTabItem extends StatelessWidget {
  const _BottomTabItem({
    required this.icon,
    required this.activeIcon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final IconData icon;
  final IconData activeIcon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);

    const activeColor = AppPalette.accent;
    final inactiveColor = palette.textSecondary;
    final color = selected ? activeColor : inactiveColor;

    return Semantics(
      label: label,
      button: true,
      selected: selected,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(22),
        child: SizedBox(
          height: 70,
          child: ExcludeSemantics(
            // 선택 상태가 바뀔 때 색과 아이콘이 부드럽게 이어지도록 합니다.
            child: TweenAnimationBuilder<double>(
              tween: Tween<double>(begin: 0, end: selected ? 1 : 0),
              duration: const Duration(milliseconds: 220),
              curve: Curves.easeOut,
              builder: (context, progress, _) {
                final animatedColor =
                    Color.lerp(inactiveColor, activeColor, progress) ?? color;

                return Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Transform.scale(
                      scale: 1 + progress * 0.08,
                      child: Icon(
                        selected ? activeIcon : icon,
                        color: animatedColor,
                        size: 25,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      label,
                      style: TextStyle(
                        color: animatedColor,
                        fontSize: 12,
                        height: 1.1,
                        fontWeight: selected
                            ? FontWeight.w700
                            : FontWeight.w500,
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ),
      ),
    );
  }
}
