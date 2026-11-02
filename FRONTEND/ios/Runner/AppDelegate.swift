import AVFoundation
import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    ScanCameraDeviceChannel.register(with: engineBridge.applicationRegistrar.messenger())
  }
}

/// 스캔 카메라가 가까운 라벨에도 초점을 맞추도록, 렌즈를 스스로 바꾸는 뒤 카메라를 알려 준다.
///
/// camera 플러그인은 렌즈 하나짜리 카메라만 고를 수 있다. Pro 아이폰의 광각은 가까우면
/// 초점이 안 맞고, 기본 카메라 앱은 이때 초광각(매크로)으로 넘어간다. 초광각이 든 가상
/// 카메라를 열면 같은 전환을 iOS 가 해 준다.
enum ScanCameraDeviceChannel {
  static func register(with messenger: FlutterBinaryMessenger) {
    let channel = FlutterMethodChannel(
      name: "kdpp/scan_camera_device", binaryMessenger: messenger)
    channel.setMethodCallHandler { call, result in
      guard call.method == "closeFocusBackCamera" else {
        result(FlutterMethodNotImplemented)
        return
      }
      result(closeFocusBackCamera())
    }
  }

  /// 초광각이 든 뒤 가상 카메라의 ID 와 광각(1x) 화각이 되는 확대 배율. 없으면 nil.
  private static func closeFocusBackCamera() -> [String: Any]? {
    let deviceTypes: [AVCaptureDevice.DeviceType] = [.builtInTripleCamera, .builtInDualWideCamera]
    for deviceType in deviceTypes {
      // 가상 카메라의 배율 1.0 은 초광각 화각이고, 첫 전환 배율에서 광각으로 넘어간다.
      guard let device = AVCaptureDevice.default(deviceType, for: .video, position: .back),
        let wideZoomFactor = device.virtualDeviceSwitchOverVideoZoomFactors.first
      else { continue }
      return ["uniqueId": device.uniqueID, "wideZoomFactor": wideZoomFactor.doubleValue]
    }
    return nil
  }
}
