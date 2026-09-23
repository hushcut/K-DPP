// 홈·스캔·옷장 탭과 상세 리포트 전환을 한 화면에서 관리하는 앱의 메인 셸입니다.
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'closet_provider.dart';
import 'closet_screen.dart';
import 'home_screen.dart';
import 'models/clothes.dart';
import 'models/main_screen_arguments.dart';
import 'navigation_bar_opacity_provider.dart';
import 'report_screen.dart';
import 'scan_screen.dart';
import 'theme/app_palette.dart';
import 'widgets/app_back_button.dart';
import 'widgets/frosted_surface.dart';
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
  // 새 화면이 들어오는 쪽(본문 크기 대비 비율)입니다. 홈·옷장은 옆에서, 스캔은 아래에서 살짝 올라옵니다.
  Offset _tabSlideBegin = const Offset(0.06, 0);

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
    // 스캔 탭은 옆에서 밀지 않습니다(2026-09-23 폰 확인: 오른쪽 위에서 밀려 나오는 것처럼 보였다).
    // 들어갈 때는 내비 바가 내려가는 것과 짝이 맞게 아래에서 4% 살짝 떠오르고(사용자 요청),
    // 나올 때는 밝기만 바뀝니다. 홈·옷장 사이에서는 가는 방향 쪽에서 들어옵니다.
    final Offset slideBegin;
    if (index == 1) {
      slideBegin = const Offset(0, 0.04);
    } else if (_selectedIndex == 1) {
      slideBegin = Offset.zero;
    } else {
      slideBegin = Offset(index >= _selectedIndex ? 0.06 : -0.06, 0);
    }

    setState(() {
      _selectedIndex = index;
      _isShowingReport = false;
      _tabSlideBegin = slideBegin;
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
      _ScanTabInsets(
        child: ScanScreen(
          isActive:
              _selectedIndex == 1 && !_isShowingReport && !_isCoveredByRoute,
        ),
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
                  begin: _tabSlideBegin,
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
        leadingWidth: 52,
        leading: Padding(
          padding: const EdgeInsets.only(left: 8),
          child: AppBackButton(
            onPressed: _closeReport,
            tooltip: '리포트 닫기',
            color: appBarIconColor,
          ),
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
      leadingWidth: 52,
      // 스캔 화면에서는 하단 내비게이션이 없으므로 나가는 버튼을 제공합니다.
      leading: _isScanTabActive
          ? Padding(
              padding: const EdgeInsets.only(left: 8),
              child: AppBackButton(
                onPressed: () => _selectTab(0),
                tooltip: '스캔 화면 닫기',
                color: appBarIconColor,
              ),
            )
          : null,
      title: const KdppLogoMark(size: 34),
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

/// 스캔 탭이 내비 바 높이 변화에 흔들리지 않도록 본문 하단 여백을 시스템 안전 영역만으로 고정합니다.
///
/// `extendBody: true`인 Scaffold는 본문의 하단 padding을 내비 바 높이로 채웁니다. 스캔 탭에서는
/// 내비 바가 사라지므로 전환 애니메이션 동안 그 값이 매 프레임 줄어들어, 남는 높이를 나눠 배치하는
/// 카메라 화면이 아래로 흘러내렸습니다(2026-09-23 폰 확인). 스캔 탭은 내비 바가 없는 상태가 기준이므로
/// 처음부터 그 기준으로 그립니다.
class _ScanTabInsets extends StatelessWidget {
  const _ScanTabInsets({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    // 키보드가 올라오면 시스템 하단 여백은 키보드에 가려지므로 Flutter의 padding 계산과 같이 뺍니다.
    final systemBottom = math.max(
      0.0,
      media.viewPadding.bottom - media.viewInsets.bottom,
    );

    return MediaQuery(
      data: media.copyWith(
        padding: media.padding.copyWith(bottom: systemBottom),
      ),
      child: child,
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
    // 화면 설정에서 고른 값(60~100%). 100% 미만이면 뒤로 스크롤되는 내용이 흐리게 비칩니다.
    final opacity = context.watch<NavigationBarOpacityProvider>().opacity;

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
                height: 70,
                child: FrostedSurface(
                  opacity: opacity,
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
                  // 누름 효과는 보이는 원에 그립니다. 원 밖(글자·여백)을 누르면
                  // 바깥 GestureDetector 가 받습니다.
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: activeColor.withValues(alpha: 0.34),
                          blurRadius: 18,
                          offset: const Offset(0, 8),
                        ),
                      ],
                    ),
                    child: Material(
                      color: selected ? AppPalette.accentPressed : activeColor,
                      shape: const CircleBorder(),
                      clipBehavior: Clip.antiAlias,
                      child: InkWell(
                        onTap: onTap,
                        child: const Icon(
                          Icons.camera_alt,
                          color: Colors.white,
                          size: 30,
                        ),
                      ),
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
