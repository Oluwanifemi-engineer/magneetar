import Foundation
import AVFoundation

/// Plays the bundled dual-tone siren at maximum volume.
///
/// Mirrors the Android app's 5s alarm burst (the server treats `alarm` as
/// urgent: priority 1, 5-minute expiry). Uses an AVAudioPlayer with the
/// siren.wav bundled in Resources — plays even while the device is locked
/// (audio session configured for playback, which is allowed in the
/// background for as long as the app holds the audio session).
final class SirenPlayer: NSObject, AVAudioPlayerDelegate {
    static let shared = SirenPlayer()

    private var player: AVAudioPlayer?
    private var playLoops = 0

    private override init() {
        super.init()
        do {
            try AVAudioSession.sharedInstance().setCategory(
                .playback,
                mode: .default,
                options: [.mixWithOthers]
            )
        } catch {
            // Non-fatal — audio may still play through the default route.
        }
    }

    /// Play the siren ~5 seconds worth (the WAV is 5s of dual-tone).
    func play() {
        guard let url = Bundle.main.url(forResource: "siren", withExtension: "wav"),
              let player = try? AVAudioPlayer(contentsOf: url) else { return }
        try? AVAudioSession.sharedInstance().setActive(true)
        player.delegate = self
        player.numberOfLoops = 0
        player.volume = 1.0
        player.play()
        self.player = player
    }

    func stop() {
        player?.stop()
        player = nil
    }

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        if self.player === player { self.player = nil }
    }
}
