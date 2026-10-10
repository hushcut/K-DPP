// 홈·옷장 탭을 한 화면에서 관리하고, 스캔·상세 리포트를 그 위에 쌓아 여는 앱의 메인 셸입니다.
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
import 'widgets/bottom_navigation_metrics.dart';
import 'widgets/frosted_surface.dart';
import 'widgets/kdpp_logo_mark.dart';

/// 하단 내비게이션의 선택 상태를 관리하고 스캔·상세 리포트·설정을 위에 쌓아 엽니다.
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

  // 탭 번호는 0 홈 · 2 옷장입니다. 1(스캔)은 탭이 아니라 위에 쌓아 여는 화면이라 여기에 들어오지 않습니다.
  int _selectedIndex = 0;
  bool _didReadInitialArgs = false;
  // 스캔 저장 직후처럼 진입하자마자 스캔 화면·리포트를 쌓아 열어야 하는지 나타냅니다.
  bool _shouldOpenInitialScan = false;
  bool _shouldOpenInitialReport = false;
  // 이 화면이 위에 쌓은 스캔·리포트·설정 라우트 수입니다. 스캔 저장 직후에는 스캔 화면과
  // 리포트가 함께 쌓이므로, 둘 다 닫혀야 덮이지 않은 것으로 봅니다.
  int _coveringRouteCount = 0;
  // 옷장이 선택 모드인지입니다. 옷장 화면이 바꾸고, 이 화면은 하단 메뉴를 숨기는 데 씁니다.
  // 한 값을 둘이 함께 보아야 어긋나지 않습니다(콜백으로 부모를 다시 그리면 빌드 중 호출이 생김).
  final ValueNotifier<bool> _closetSelectionMode = ValueNotifier<bool>(false);

  // 탭을 바꿀 때마다 새 화면이 부드럽게 나타나도록 재생하는 전환 애니메이션입니다.
  late final AnimationController _tabTransitionController;
  late final Animation<double> _tabTransition;
  // 새 화면이 들어오는 쪽(본문 크기 대비 비율)입니다. 가는 방향 쪽 옆에서 들어옵니다.
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
    _closetSelectionMode.dispose();
    super.dispose();
  }

  void _selectTab(int index) {
    if (index < 0 || index >= _tabCount) return;

    if (index == 1) {
      _openScan();
      return;
    }

    final isSameView = index == _selectedIndex;
    final slideBegin = Offset(index >= _selectedIndex ? 0.06 : -0.06, 0);

    setState(() {
      _selectedIndex = index;
      _tabSlideBegin = slideBegin;
    });

    // 같은 탭을 다시 누른 경우에는 굳이 다시 재생하지 않습니다.
    if (!isSameView) {
      _tabTransitionController.forward(from: 0);
    }
  }

  bool get _isCoveredByRoute => _coveringRouteCount > 0;

  // 스캔 화면을 탭 위에 쌓아 엽니다. 리포트·설정처럼 라우트라서 iOS 에서 왼쪽 끝을 밀어 닫을 수 있고,
  // 하단 메뉴까지 덮으며, 닫으면 들어왔던 탭으로 돌아갑니다(2026-09-26 사용자 결정 A안).
  void _openScan() {
    // 설정과 같은 방어입니다. 쌓이는 동안엔 라우트 장벽이 아래 탭을 막아 보통은 걸리지 않습니다.
    if (_isCoveredByRoute) return;

    // 탭 트리가 유지되므로, 검색창 등에 남은 포커스와 키보드를 먼저 정리합니다.
    FocusManager.instance.primaryFocus?.unfocus();
    _pushScan();
  }

  Future<void> _pushScan() {
    return _pushCoveringRoute(
      () => Navigator.push<void>(
        context,
        MaterialPageRoute<void>(builder: (_) => const _ScanPage()),
      ),
    );
  }

  // 선택 의류를 Provider에 기록한 뒤 상세 리포트를 탭 위에 쌓아 엽니다.
  // 설정처럼 라우트로 열어야 iOS 에서 왼쪽 끝을 밀어 닫을 수 있습니다(2026-09-24 사용자 결정).
  void _openReport(Clothes item) {
    // 설정과 같은 방어입니다. 쌓이는 동안엔 라우트 장벽이 아래 탭을 막아 보통은 걸리지 않습니다.
    if (_isCoveredByRoute) return;

    // 탭 트리가 유지되므로, 검색창 등에 남은 포커스와 키보드를 먼저 정리합니다.
    FocusManager.instance.primaryFocus?.unfocus();
    context.read<ClosetProvider>().selectClothes(item);
    _pushReport();
  }

  Future<void> _pushReport() {
    return _pushCoveringRoute(
      () => Navigator.push<void>(
        context,
        MaterialPageRoute<void>(
          builder: (_) => _ReportPage(onDeleted: _handleReportDeleted),
        ),
      ),
    );
  }

  // 리포트에서 의류를 지우면 리포트가 닫히면서 옷장 탭이 보이게 합니다.
  // 스캔 저장 직후처럼 스캔 화면 위에 열린 리포트였다면 스캔 화면도 함께 닫습니다.
  void _handleReportDeleted() {
    final mainRoute = ModalRoute.of(context);
    if (mainRoute != null) {
      Navigator.popUntil(context, (route) => route == mainRoute);
    }

    setState(() {
      _selectedIndex = 2;
    });
  }

  // 위에 쌓은 라우트가 닫힐 때까지 옷장 탭이 비활성이도록 열림 상태를 추적합니다.
  Future<void> _pushCoveringRoute(Future<Object?> Function() push) async {
    setState(() {
      _coveringRouteCount++;
    });

    await push();

    if (!mounted) return;

    setState(() {
      _coveringRouteCount--;
    });
  }

  int _normalizeInitialIndex(int index) {
    if (index == 3) return 2;

    // 스캔(1)은 홈 위에 쌓아 열므로 아래에는 홈을 둡니다.
    if (index == 0 || index == 2) {
      return index;
    }

    return 0;
  }

  /// 외부 경로에서 전달된 초기 탭과 스캔·리포트 표시 요청을 한 번만 적용합니다.
  void _applyInitialArguments(Object? args) {
    final int requestedIndex;
    if (args is MainScreenArguments) {
      requestedIndex = args.initialIndex;
      _shouldOpenInitialReport =
          args.showReport &&
          context.read<ClosetProvider>().currentReportItem != null;
    } else {
      requestedIndex = args is int ? args : 0;
    }

    _shouldOpenInitialScan = requestedIndex == 1;
    _selectedIndex = _normalizeInitialIndex(requestedIndex);
  }

  Future<void> _openSettings() async {
    // 빠른 연속 탭으로 설정 화면이 두 번 쌓이지 않게 합니다.
    if (_isCoveredByRoute) return;

    await _pushCoveringRoute(() => Navigator.pushNamed(context, '/settings'));
  }

  List<Widget> _buildTabScreens() {
    return [
      HomeScreen(
        onStartScan: _openScan,
        onOpenReport: _openReport,
        onOpenCloset: () => _selectTab(2),
      ),
      ClosetScreen(
        isActive: _selectedIndex == 2 && !_isCoveredByRoute,
        selectionMode: _closetSelectionMode,
        onOpenReport: _openReport,
        onStartScan: _openScan,
      ),
    ];
  }

  // 탭을 유지한 채(작성 중인 내용 보존) 화면만 부드럽게 나타나게 합니다.
  // 스캔·리포트·설정은 이 화면 위에 라우트로 쌓이므로 탭 트리는 그대로 남습니다.
  Widget _buildBody() {
    return FadeTransition(
      opacity: _tabTransition,
      child: SlideTransition(
        position: Tween<Offset>(
          begin: _tabSlideBegin,
          end: Offset.zero,
        ).animate(_tabTransition),
        child: IndexedStack(
          // 탭 번호(0 홈 · 2 옷장)를 스택 위치로 바꿉니다.
          index: _selectedIndex == 2 ? 1 : 0,
          children: _buildTabScreens(),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_didReadInitialArgs) {
      final args =
          widget.initialArguments ?? ModalRoute.of(context)?.settings.arguments;
      _applyInitialArguments(args);
      _didReadInitialArgs = true;

      if (_shouldOpenInitialScan || _shouldOpenInitialReport) {
        // 빌드 중에는 라우트를 쌓을 수 없으므로 첫 프레임 뒤에 엽니다. 스캔 저장 직후에는 새 스캔 화면
        // 위에 리포트를 쌓아, 리포트를 닫으면 바로 다음 옷을 찍을 수 있게 합니다.
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted) return;

          if (_shouldOpenInitialScan) _pushScan();
          if (_shouldOpenInitialReport) _pushReport();
        });
      }
    }

    final palette = AppPalette.of(context);
    final scaffoldBg = palette.background;

    return Scaffold(
      backgroundColor: scaffoldBg,
      extendBody: true,
      appBar: _buildMainAppBar(context, onOpenSettings: _openSettings),
      body: _buildBody(),
      // 옷장 선택 모드에서는 메뉴를 아래로 밀어 숨기고 그 자리에 옷장의 휴지통이 섭니다(2026-10-01).
      // 높이는 그대로 두어야 본문 아래 여백(= 메뉴 자리)이 출렁이지 않고 휴지통 위치도 맞습니다.
      bottomNavigationBar: ValueListenableBuilder<bool>(
        valueListenable: _closetSelectionMode,
        builder: (context, selecting, navigationBar) => _HideableBottomBar(
          hidden: _selectedIndex == 2 && selecting,
          child: navigationBar!,
        ),
        child: _KDppBottomNavigationBar(
          selectedIndex: _selectedIndex,
          onSelect: _selectTab,
        ),
      ),
    );
  }
}

// 위 막대 아이콘 색입니다. 설정 아이콘과 스캔 화면의 "<" 가 같은 색을 씁니다.
Color _appBarIconColor(BuildContext context) {
  final isDark = Theme.of(context).brightness == Brightness.dark;
  return isDark ? Colors.white : const Color(0xFF1A1A1A);
}

/// 메인 화면과 스캔 화면이 함께 쓰는 위 막대(가운데 로고, 오른쪽 설정)입니다.
PreferredSizeWidget _buildMainAppBar(
  BuildContext context, {
  required VoidCallback onOpenSettings,
  Widget? leading,
}) {
  return AppBar(
    toolbarHeight: 56,
    backgroundColor: Colors.transparent,
    elevation: 0,
    scrolledUnderElevation: 0,
    automaticallyImplyLeading: false,
    centerTitle: true,
    leadingWidth: 52,
    leading: leading,
    title: const KdppLogoMark(size: 34),
    actions: [
      IconButton(
        onPressed: onOpenSettings,
        tooltip: '설정',
        icon: Icon(Icons.settings_outlined, color: _appBarIconColor(context)),
      ),
      const SizedBox(width: 8),
    ],
  );
}

/// 탭 위에 쌓아 여는 스캔 화면입니다.
///
/// 라우트라서 "<"·시스템 뒤로가기·iOS 왼쪽 끝 밀기로 닫히고, 하단 메뉴까지 덮습니다.
/// 결과를 입력하는 동안에는 [ScanScreen] 이 곧바로 닫히지 않게 막고 버릴지 묻습니다.
class _ScanPage extends StatelessWidget {
  const _ScanPage();

  @override
  Widget build(BuildContext context) {
    final route = ModalRoute.of(context);
    // 설정·리포트·시트처럼 다른 라우트가 위에 쌓이면 카메라를 끕니다. 이 화면이 닫히는 중(밀어서 닫기
    // 포함)에는 isActive 가 false 라 덮인 것으로 보지 않고, 카메라가 화면과 함께 사라지게 둡니다.
    final isCovered = route != null && route.isActive && !route.isCurrent;

    return Scaffold(
      backgroundColor: AppPalette.of(context).background,
      appBar: _buildMainAppBar(
        context,
        leading: Padding(
          padding: const EdgeInsets.only(left: 8),
          child: AppBackButton(
            // pop 이 아니라 maybePop 이라야 결과 입력 중 확인(ScanScreen 의 PopScope)을 거칩니다.
            onPressed: () => Navigator.maybePop(context),
            tooltip: '스캔 화면 닫기',
            color: _appBarIconColor(context),
          ),
        ),
        onOpenSettings: () {
          // 빠른 연속 탭으로 설정 화면이 두 번 쌓이지 않게 합니다.
          if (ModalRoute.of(context)?.isCurrent == false) return;

          Navigator.pushNamed(context, '/settings');
        },
      ),
      body: ScanScreen(isActive: !isCovered),
    );
  }
}

/// 탭 위에 쌓아 여는 상세 리포트 화면입니다.
///
/// 라우트라서 "<"·시스템 뒤로가기·iOS 왼쪽 끝 밀기로 닫히고, 하단 메뉴까지 덮습니다.
class _ReportPage extends StatelessWidget {
  const _ReportPage({required this.onDeleted});

  /// 의류를 지워 리포트가 닫힌 뒤 메인 화면이 할 일입니다.
  final VoidCallback onDeleted;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final appBarIconColor = isDark ? Colors.white : const Color(0xFF1A1A1A);

    return Scaffold(
      backgroundColor: AppPalette.of(context).background,
      // 앱바 높이는 기본값(56)이라 "<" 가 설정·스캔 화면과 같은 높이에 온다(2026-10-05 Android 확인 —
      // 44 일 때는 6dp 위에 있었다).
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        leadingWidth: 52,
        leading: Padding(
          padding: const EdgeInsets.only(left: 8),
          child: AppBackButton(tooltip: '리포트 닫기', color: appBarIconColor),
        ),
        title: Text(
          '상세 리포트',
          style: TextStyle(
            color: appBarIconColor,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      body: ReportScreen(
        onDeleted: () {
          Navigator.pop(context);
          onDeleted();
        },
      ),
    );
  }
}

/// 하단 메뉴를 자리(높이)는 남긴 채 아래로 밀어 숨깁니다.
///
/// 숨은 동안에는 누를 수 없고, 낭독기·키보드 초점에서도 빠집니다.
/// 높이를 줄이는 방식(AnimatedSize)은 본문 아래 여백이 함께 줄어 목록이 출렁입니다.
class _HideableBottomBar extends StatelessWidget {
  const _HideableBottomBar({required this.hidden, required this.child});

  final bool hidden;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      ignoring: hidden,
      child: ExcludeSemantics(
        excluding: hidden,
        child: ExcludeFocus(
          excluding: hidden,
          child: AnimatedSlide(
            // 메뉴 높이만큼(1.0)만 내리면 위로 번지는 스캔 버튼 그림자가 화면 아래 끝에 비칩니다.
            offset: hidden ? const Offset(0, 1.3) : Offset.zero,
            duration: _MainScreenState._transitionDuration,
            curve: Curves.easeOutCubic,
            child: child,
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
        padding: const EdgeInsets.fromLTRB(
          BottomNavigationMetrics.horizontalMargin,
          0,
          BottomNavigationMetrics.horizontalMargin,
          BottomNavigationMetrics.bottomMargin,
        ),
        child: SizedBox(
          height: BottomNavigationMetrics.boxHeight,
          child: Stack(
            clipBehavior: Clip.none,
            alignment: Alignment.bottomCenter,
            children: [
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                height: BottomNavigationMetrics.barHeight,
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

// 스캔 화면을 여는 가운데 원형 카메라 버튼입니다. 스캔은 위에 쌓는 화면이라 선택 상태가 없습니다.
class _CenterScanButton extends StatelessWidget {
  const _CenterScanButton({required this.pageBg, required this.onTap});

  final Color pageBg;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final palette = AppPalette.of(context);
    const activeColor = AppPalette.accent;

    return Semantics(
      label: '스캔',
      button: true,
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
                      color: activeColor,
                      shape: const CircleBorder(),
                      clipBehavior: Clip.antiAlias,
                      child: InkWell(
                        onTap: onTap,
                        // 누르는 동안 진한 파랑으로 어두워집니다. 짧은 탭은 강조가
                        // 칠해지기 전에 끝나 물결만 보이므로 물결도 같은 색으로 칠하고,
                        // Android 도 반짝이 대신 iOS 와 같은 원형 물결을 씁니다.
                        highlightColor: AppPalette.accentPressed,
                        splashColor: AppPalette.accentPressed,
                        splashFactory: InkRipple.splashFactory,
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
                        color: palette.textSecondary,
                        fontSize: 12,
                        height: 1.1,
                        fontWeight: FontWeight.w500,
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
