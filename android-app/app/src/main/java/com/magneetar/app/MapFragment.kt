package com.magneetar.app

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import okhttp3.*
import org.json.JSONObject
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.OnlineTileSourceBase
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.tileprovider.tilesource.XYTileSource
import org.osmdroid.util.GeoPoint
import org.osmdroid.util.MapTileIndex
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.TilesOverlay
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Map tab — dual basemaps on osmdroid.
 *
 * Satellite mode uses Esri World Imagery via the [OnlineTileSourceBase]
 * override below (Esri serves Y/X order — the reverse of the standard XYZ
 * slippy scheme — which is why a custom source is required), with a
 * World_Transportation overlay on top so street paths stay visible over the
 * imagery. Tile probing (Sep 2026) showed Esri's native imagery depth is
 * per-area — rural Nigeria tops out at z18, dense cities at z19 — and its
 * reference-labels layer is retired (all-transparent tiles), so maxZoom is
 * capped at 19: beyond native depth the map shows upsampled imagery without
 * ever requesting nonexistent tiles (the old "map not available" state).
 */
class MapFragment : Fragment() {

    private var osmMap: MapView? = null
    private var progressMap: ProgressBar? = null
    private var satelliteOverlay: TilesOverlay? = null
    private var transportOverlay: TilesOverlay? = null
    private var btnSatellite: TextView? = null
    private var tvMapDeviceName: TextView? = null
    private var tvMapDeviceModel: TextView? = null
    private var tvMapDeviceBadge: TextView? = null
    private var tvStatLat: TextView? = null
    private var tvStatLng: TextView? = null
    private var tvStatBattery: TextView? = null
    private var tvStatStatus: TextView? = null
    private var satelliteOn = false

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    /** Esri World Imagery — Z/Y/X tile order, native detail to z19. */
    private val esriWorldImagery = object : OnlineTileSourceBase(
        "Esri World Imagery", 0, 19, 256, ".jpg",
        arrayOf("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/")
    ) {
        override fun getTileURLString(pMapTileIndex: Long): String =
            baseUrl + MapTileIndex.getZoom(pMapTileIndex) + "/" +
                MapTileIndex.getY(pMapTileIndex) + "/" +
                MapTileIndex.getX(pMapTileIndex) + mImageFilenameEnding
    }

    private val esriTransportation by lazy {
        XYTileSource(
            "Esri Transportation", 0, 19, 256, ".png",
            arrayOf("https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/")
        )
    }

    // Esri's World_Boundaries_and_Places labels layer was probed dead
    // (all-transparent tiles even over dense cities) — not loaded, so no
    // place names in satellite mode. Imagery + roads only.

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View? {
        return inflater.inflate(R.layout.fragment_map, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        osmMap = view.findViewById(R.id.osm_map)
        progressMap = view.findViewById(R.id.progress_map)
        btnSatellite = view.findViewById(R.id.btn_satellite)
        tvMapDeviceName = view.findViewById(R.id.tv_map_device_name)
        tvMapDeviceModel = view.findViewById(R.id.tv_map_device_model)
        tvMapDeviceBadge = view.findViewById(R.id.tv_map_device_badge)
        tvStatLat = view.findViewById(R.id.tv_stat_lat)
        tvStatLng = view.findViewById(R.id.tv_stat_lng)
        tvStatBattery = view.findViewById(R.id.tv_stat_battery)
        tvStatStatus = view.findViewById(R.id.tv_stat_status)

        Configuration.getInstance().userAgentValue = requireContext().packageName

        osmMap?.let { map ->
            map.setTileSource(TileSourceFactory.MAPNIK)
            map.setMultiTouchControls(true)
            map.controller.setZoom(16.0)
            map.controller.setCenter(GeoPoint(7.518, 4.528))
            // Esri native depth is 18 (rural) / 19 (cities). Capping at 19
            // means osmdroid upsamples the deepest available imagery instead
            // of requesting placeholder tiles beyond the source's coverage.
            map.maxZoomLevel = 19.0
            map.minZoomLevel = 3.0
            map.invalidate()
        }

        buildSatelliteOverlays()
        wireControls(view)
        loadDeviceLocation()
    }

    private fun buildSatelliteOverlays() {
        val map = osmMap ?: return

        // Satellite imagery sits in an overlay *above* Mapnik so a toggle is
        // instant (no tile-source reload); we hide it by default.
        satelliteOverlay = TilesOverlay(
            org.osmdroid.tileprovider.MapTileProviderBasic(requireContext(), esriWorldImagery),
            context
        ).apply {
            setLoadingBackgroundColor(android.graphics.Color.TRANSPARENT)
            setEnabled(false)
            map.overlays.add(this)
        }

        transportOverlay = TilesOverlay(
            org.osmdroid.tileprovider.MapTileProviderBasic(requireContext(), esriTransportation),
            context
        ).apply {
            setEnabled(false)
            map.overlays.add(this)
        }


    }

    private fun wireControls(view: View) {
        view.findViewById<ImageButton>(R.id.btn_zoom_in).setOnClickListener {
            osmMap?.controller?.zoomIn()
        }
        view.findViewById<ImageButton>(R.id.btn_zoom_out).setOnClickListener {
            osmMap?.controller?.zoomOut()
        }
        btnSatellite?.setOnClickListener { toggleSatellite() }
    }

    private fun toggleSatellite() {
        satelliteOn = !satelliteOn
        satelliteOverlay?.setEnabled(satelliteOn)
        transportOverlay?.setEnabled(satelliteOn)
        btnSatellite?.text = if (satelliteOn) "MAP" else "SAT"
        btnSatellite?.setTextColor(
            ContextCompat.getColor(
                requireContext(),
                if (satelliteOn) R.color.accent_aubergine else R.color.text_secondary
            )
        )
        osmMap?.invalidate()
    }

    override fun onResume() {
        super.onResume()
        osmMap?.onResume()
        loadDeviceLocation()
    }

    override fun onPause() {
        super.onPause()
        osmMap?.onPause()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        osmMap?.onDetach()
        osmMap = null
        satelliteOverlay = null
        transportOverlay = null
    }

    private fun loadDeviceLocation() {
        val prefs = requireContext().getSharedPreferences("mt", 0)
        val serverUrl = prefs.getString("server_url", "") ?: ""
        val userToken = TokenVault.accessToken(requireContext())

        if (serverUrl.isEmpty() || userToken.isEmpty()) return

        val request = Request.Builder()
            .url("$serverUrl/api/dashboard/devices")
            .addHeader("Authorization", "Bearer $userToken")
            .get()
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {}
            override fun onResponse(call: Call, response: Response) {
                val body = response.body?.string() ?: return
                activity?.runOnUiThread {
                    try {
                        val json = JSONObject(body)
                        val arr = json.optJSONArray("devices") ?: return@runOnUiThread
                        if (arr.length() == 0) return@runOnUiThread

                        val device = arr.getJSONObject(0)
                        // Server contract (dashboard_devices.py) is lat/lng.
                        val lat = device.optDouble("lat", 0.0)
                        val lng = device.optDouble("lng", 0.0)
                        val name = device.optString("alias", device.optString("model", "Device"))
                        val model = device.optString("model", "")
                        val isOnline = device.optBoolean("is_online", false)
                        val battery = device.optInt("battery_percent", -1)

                        // Status card + stats strip (mono readouts per design)
                        tvMapDeviceName?.text = name
                        tvMapDeviceModel?.text = model.ifEmpty { "—" }
                        val statusColor = ContextCompat.getColor(
                            requireContext(),
                            if (isOnline) R.color.status_online else R.color.status_offline
                        )
                        val statusText = if (isOnline) "ONLINE" else "OFFLINE"
                        tvMapDeviceBadge?.text = statusText
                        tvMapDeviceBadge?.setTextColor(statusColor)
                        tvStatStatus?.text = statusText
                        tvStatStatus?.setTextColor(statusColor)
                        tvStatBattery?.text = if (battery >= 0) "$battery%" else "—"
                        tvStatBattery?.setTextColor(
                            ContextCompat.getColor(
                                requireContext(),
                                when {
                                    battery > 20 -> R.color.status_online
                                    battery > 0 -> R.color.alert_warning
                                    else -> R.color.text_secondary
                                }
                            )
                        )

                        if (lat != 0.0 && lng != 0.0) {
                            tvStatLat?.text = String.format("%.5f°", lat)
                            tvStatLng?.text = String.format("%.5f°", lng)
                            osmMap?.let { map ->
                                map.overlays.removeAll { it is Marker }
                                val marker = Marker(map)
                                marker.position = GeoPoint(lat, lng)
                                marker.title = name
                                marker.setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                                marker.icon = ContextCompat.getDrawable(requireContext(), R.drawable.map_marker_blue)
                                map.overlays.add(marker)
                                map.controller.animateTo(GeoPoint(lat, lng))
                                map.invalidate()
                            }
                        } else {
                            tvStatLat?.text = "—"
                            tvStatLng?.text = "—"
                        }
                    } catch (_: Exception) {}
                }
            }
        })
    }
}
