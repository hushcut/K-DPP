import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

/// 순서 바꾸기 목록에서 끌고 있는 카드가 다른 카드를 밀어낼 때마다 가벼운 틱을 줍니다.
///
/// Flutter 의 순서 바꾸기 목록은 집어 들 때(`onReorderStart`)와 내려놓을 때(`onReorderEnd`)만
/// 알려 주고, 끄는 도중 카드가 비켜 서는 순간은 알려 주지 않습니다. 그 판정을 따라 계산하면
/// 공개되지 않은 값(각 카드의 목표 위치·등록 순서·자동 스크롤 시점)에 맞춰야 해서 어긋나기 쉽습니다.
/// 그래서 목록 안 카드가 실제로 움직이기 시작하는 프레임을 봅니다. 스크롤로 움직인 만큼은 빼고
/// 보므로 자동 스크롤 중에도 비켜 서는 카드에만 반응합니다.
///
/// 순서 바꾸기 중 각 카드는 제자리와 한쪽으로 비켜 선 자리, 두 곳 사이만 오갑니다
/// (flutter/widgets/reorderable_list.dart `updateForGap`). 그래서 움직이는 방향이 직전 움직임과
/// 달라지는 순간이 곧 새로 밀려나거나 되돌아오는 순간입니다. 도중에 되돌아가도 제 위치에서
/// 반대로 움직이므로 같은 규칙으로 잡힙니다. 세로 목록(위에서 아래로)만 다룹니다.
class ReorderBumpTracker {
  // 이보다 작은 흔들림은 움직임으로 치지 않습니다(논리 픽셀).
  static const double _minMovement = 0.5;

  final Set<_ReorderBumpProbeState> _probes = <_ReorderBumpProbeState>{};
  bool _active = false;
  bool _checkScheduled = false;

  /// 카드를 집어 들 때 부릅니다. 그 뒤 첫 프레임의 자리를 기준으로 삼습니다.
  void start() {
    _active = true;
    for (final probe in _probes) {
      probe._resetTracking();
    }
    _scheduleCheck();
  }

  /// 카드를 내려놓을 때와 목록이 사라질 때 부릅니다. 끄는 동안에만 프레임마다 살펴봅니다.
  void stop() {
    _active = false;
  }

  // 프레임을 새로 요청하지 않고, 끄는 동안 그려지는 프레임마다 한 번씩 봅니다.
  void _scheduleCheck() {
    if (_checkScheduled) return;
    _checkScheduled = true;
    SchedulerBinding.instance.addPostFrameCallback((_) {
      _checkScheduled = false;
      if (!_active) return;
      _check();
      _scheduleCheck();
    });
  }

  void _check() {
    var bumped = false;
    for (final probe in _probes) {
      // 한 프레임에 여러 장이 밀려도 모두 확인해 각 카드의 방향 기록을 맞춰 둡니다.
      if (probe._observe()) bumped = true;
    }
    // 한 프레임에 여러 장이 함께 밀리면 틱은 한 번만 줍니다.
    if (bumped) HapticFeedback.selectionClick();
  }
}

/// [ReorderBumpTracker] 가 지켜볼 목록 카드 하나를 감쌉니다.
///
/// 끌고 있는 카드의 복사본(화면 위 오버레이)은 목록 밖이라 저절로 빠집니다.
class ReorderBumpProbe extends StatefulWidget {
  const ReorderBumpProbe({
    super.key,
    required this.tracker,
    required this.child,
  });

  final ReorderBumpTracker tracker;
  final Widget child;

  @override
  State<ReorderBumpProbe> createState() => _ReorderBumpProbeState();
}

class _ReorderBumpProbeState extends State<ReorderBumpProbe> {
  ScrollableState? _scrollable;
  double? _lastOffset;
  int _lastDirection = 0;

  @override
  void initState() {
    super.initState();
    widget.tracker._probes.add(this);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _scrollable = Scrollable.maybeOf(context);
  }

  @override
  void didUpdateWidget(covariant ReorderBumpProbe oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.tracker != widget.tracker) {
      oldWidget.tracker._probes.remove(this);
      widget.tracker._probes.add(this);
      _resetTracking();
    }
  }

  @override
  void dispose() {
    widget.tracker._probes.remove(this);
    super.dispose();
  }

  void _resetTracking() {
    _lastOffset = null;
    _lastDirection = 0;
  }

  // 목록 내용 기준 위치(스크롤로 움직인 만큼을 뺀 위치)입니다. 목록 밖이면 null.
  double? _contentOffset() {
    final scrollable = _scrollable;
    final box = context.findRenderObject();
    if (scrollable == null ||
        !scrollable.position.hasPixels ||
        box is! RenderBox ||
        !box.attached ||
        !box.hasSize) {
      return null;
    }

    return box.localToGlobal(Offset.zero).dy + scrollable.position.pixels;
  }

  /// 이번 프레임에 이 카드가 새로 밀려나거나 되돌아가기 시작했으면 true.
  bool _observe() {
    final offset = _contentOffset();
    if (offset == null) return false;

    final last = _lastOffset;
    _lastOffset = offset;
    if (last == null) return false;

    final delta = offset - last;
    if (delta.abs() < ReorderBumpTracker._minMovement) return false;

    final direction = delta > 0 ? 1 : -1;
    final startedNewMove = direction != _lastDirection;
    _lastDirection = direction;
    return startedNewMove;
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
