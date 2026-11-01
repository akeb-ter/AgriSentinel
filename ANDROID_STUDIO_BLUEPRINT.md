# AgriSentinel Native Android App — Complete Android Studio Blueprint

This document contains everything you need to build the **AgriSentinel Native Android App** in **Android Studio** (Kotlin + Jetpack Compose + CameraX + Retrofit/OkHttp + WebSocket Push Notifications).

It includes:
1. **Copy-Paste Master Prompt** for **Gemini in Android Studio** (or Claude / Cursor) to generate the project structure automatically.
2. **Gradle & Manifest Configurations** (including `network_security_config.xml` so Android allows cleartext HTTP connections to `http://agrisentinel.local:8000` and local Raspberry Pi IP addresses).
3. **Complete API Contract & Data Models** matching your Raspberry Pi FastAPI backend (`edge/web_app.py`).
4. **Full Ready-to-Paste Kotlin Source Code** for mDNS/Hotspot Auto-Discovery, Persistent Session Cookie Auth, Live 30 FPS MJPEG Stream Viewer, CameraX Native Scouting (zero HTTPS restrictions), WebSocket Push Notification Service, and the 4-Tab Jetpack Compose UI.

---

## 1. Copy-Paste Master Prompt for Android Studio AI (Gemini)

> **Instructions**: Open Android Studio -> Create a **New Project** -> Select **Empty Activity (Jetpack Compose)** -> Package name `com.agrisentinel.mobile` -> Minimum SDK **API 26 (Android 8.0)**. Then open the **Gemini** panel in Android Studio (or your AI coding assistant) and paste the prompt block below:

```markdown
Build a complete, production-grade Native Android application in Kotlin and Jetpack Compose for **AgriSentinel (Smart Crop Probe — AI Pest Detection & Pesticide Advisor)** with package name `com.agrisentinel.mobile`.

### Core Architecture & Requirements:
1. **Probe Discovery & Connection Management**:
   - Auto-discover the Raspberry Pi probe via mDNS (`http://agrisentinel.local:8000`) and Raspberry Pi Hotspot fallback (`http://192.168.4.1:8000`), while allowing manual IP/Host profiles saved in SharedPreferences.
   - Verify connectivity via `GET /api/ping` and authenticate via `POST /login` (form-urlencoded `username` & `password`), storing the `agrisentinel_session` cookie in a persistent OkHttp `CookieJar`.
   - Configure `network_security_config.xml` and `usesCleartextTraffic="true"` in `AndroidManifest.xml` so HTTP connections to local probe IPs and `.local` domains work without SSL/HTTPS errors.

2. **Native CameraX Scouting (No Browser HTTPS Restriction)**:
   - Use Android `CameraX` (`PreviewView` + `ImageCapture`) and Android Photo Picker (`ActivityResultContracts.GetContent`) so farmers can snap crop photos with the phone camera or pick from gallery over local Wi-Fi without needing HTTPS.
   - Optionally attach phone GPS coordinates (`FusedLocationProviderClient`) to the plot/farm area tag.
   - Upload captured/selected images via multipart `POST /api/detect/upload` with fields: `file`, `crop_type`, `conf_threshold`, `model_profile`, and `source="phone_camera"`.

3. **Real-Time WebSocket Alerts & Rich Push Notifications**:
   - Maintain a WebSocket connection to `ws://<host>:8000/ws/alerts`.
   - On `PEST_DETECTION_ALERT`, trigger a high-priority Android Notification (`NotificationCompat.BigPictureStyle` showing the cropped pest ROI image from `crop_image_path`), trigger a haptic vibration (`VibrationEffect`), and play an alert tone.

4. **4-Tab Material3 Bottom Navigation Layout** (Dark/Emerald Agricultural Theme):
   - **Tab 1: Scout & PTZ (`ScoutScreen`)**:
     - Top bar with connection status pill, active Host Crop selector (`auto`, `rice`, `corn`, `wheat`, `citrus`, `mango`), AI Model Profile selector (`comprehensive_102`, `tropical_27`, `cereal_crops`, `quarrying_insect`), and Confidence Threshold slider (`0.15` to `0.60`).
     - Mode Switcher: **Probe Live Stream + FEELWORLD 4K10X PTZ Controls** vs **Phone CameraX Scouting & Gallery Upload**.
     - In Probe Mode: Render the live MJPEG stream (`GET /video_feed`, `multipart/x-mixed-replace; boundary=frame`), Live AI toggle (`POST /api/vision/live_toggle`), Instant Capture button (`POST /api/analyze`), and FEELWORLD 4K10X PTZ D-Pad (`pan_left`, `pan_right`, `tilt_up`, `tilt_down`, `home`), 1.0x–10.0x Optical Zoom slider (`POST /api/ptz/move`), Canopy Presets P1–P4 (`POST /api/ptz/preset`), and Auto-Patrol selector (`POST /api/ptz/patrol`).
     - In Phone Mode: Native CameraX viewfinder, shutter button, and gallery upload button with instant AI analysis.
     - Diagnostic Result Card: Displays Dual Snapshots side-by-side (**Uncropped Full Scene** + **Cropped Pest Close-Up ROI**), Plant Health status, Infestation Severity badge, and a **Multi-Pest Recommendations Bar** (species filter pills + stacked chemical, organic biocontrol, PHI, and safety PPE cards).
   - **Tab 2: Pesticide Advisor (`AdvisorScreen`)**:
     - Populated from `GET /api/crops`. Allows selecting a Crop and any of its 20 IP102 Pest Species.
     - Queries `GET /api/recommendations/{crop}/{pest}?confidence=0.90`.
     - Displays side-by-side **Reference Specimen Image** (`images.reference_url` with SVG fallback `images.svg_fallback_url` loaded via Coil SVG decoder) and **Latest Farm Field Capture** (`images.latest_field_capture.url`).
     - Displays Symptoms & Diagnostic Cues (`affected_part`, `primary_symptom`, `visual_cues`), Chemical Pesticide, Dosage & PHI, Organic Alternative, Safety Precautions, and FAO/IRRI Citation.
   - **Tab 3: Inspection History (`HistoryScreen`)**:
     - Queries `GET /api/detections` with pagination and filters (`crop`, `infestation`, `search`).
     - Renders cards with **Dual Thumbnails** (`image_path` Full frame + `crop_image_path` ROI macro). Tapping opens a full-screen dual zoom dialog.
     - Supports multi-select Batch Delete (`POST /api/detections/batch_delete`) and Password-Protected Clear History (`POST /api/detections/clear` requiring user's account password).
   - **Tab 4: Farm Analytics (`AnalyticsScreen`)**:
     - Queries `GET /api/stats`.
     - Displays 4 KPI summary cards (`total_inspections`, `severe_alerts`, `harmful_pest_count`, `pest_free_count` + `beneficial_count`) and 3 visual progress bar distribution cards (`top_pests`, `crop_distribution`, `severity_breakdown`).
```

---

## 2. Gradle & Android Manifest Configuration

### 2.1 `app/build.gradle.kts` (Module-level)

Add the following dependencies in `app/build.gradle.kts`:

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.agrisentinel.mobile"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.agrisentinel.mobile"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
    }

    buildFeatures {
        compose = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // Jetpack Compose & Material3
    val composeBom = platform("androidx.compose:compose-bom:2024.10.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")

    // Networking: Retrofit2, OkHttp3, Gson & WebSocket
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-gson:2.11.0")

    // Image Loading (Coil + SVG support for offline taxonomic specimen cards)
    implementation("io.coil-kt:coil-compose:2.7.0")
    implementation("io.coil-kt:coil-svg:2.7.0")

    // CameraX for native phone field scouting
    val cameraxVersion = "1.4.0"
    implementation("androidx.camera:camera-core:$cameraxVersion")
    implementation("androidx.camera:camera-camera2:$cameraxVersion")
    implementation("androidx.camera:camera-lifecycle:$cameraxVersion")
    implementation("androidx.camera:camera-view:$cameraxVersion")

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    // Optional GPS Location for field scouting plot coordinates
    implementation("com.google.android.gms:play-services-location:21.3.0")
}
```

---

### 2.2 `app/src/main/res/xml/network_security_config.xml`

> [!IMPORTANT]
> Android 9+ blocks `http://` (cleartext) traffic by default. Since the Raspberry Pi runs locally on `http://agrisentinel.local:8000` or `http://192.168.x.x:8000`, create `app/src/main/res/xml/network_security_config.xml` to permit local HTTP and WebSocket connections.

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="true">
        <trust-anchors>
            <certificates src="system" />
        </trust-anchors>
    </base-config>
</network-security-config>
```

---

### 2.3 `app/src/main/AndroidManifest.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <!-- Network & mDNS Discovery -->
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
    <uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE" />

    <!-- Native Phone Camera Scouting -->
    <uses-feature android:name="android.hardware.camera.any" android:required="false" />
    <uses-permission android:name="android.permission.CAMERA" />

    <!-- Alerts, Vibration & Optional GPS Tagging -->
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
    <uses-permission android:name="android.permission.VIBRATE" />
    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />

    <application
        android:allowBackup="true"
        android:label="AgriSentinel"
        android:supportsRtl="true"
        android:usesCleartextTraffic="true"
        android:networkSecurityConfig="@xml/network_security_config"
        android:theme="@android:style/Theme.Material.NoActionBar">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:configChanges="orientation|screenSize|screenLayout">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

---

## 3. Complete Kotlin Data Models & API Interface (`AgriSentinelApi.kt`)

Create `app/src/main/java/com/agrisentinel/mobile/network/AgriSentinelApi.kt`:

```kotlin
package com.agrisentinel.mobile.network

import com.google.gson.annotations.SerializedName
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.*

// ─── Data Models ────────────────────────────────────────────────

data class PingResponse(
    val status: String,
    val service: String?,
    val probe_id: String?
)

data class StatusResponse(
    val status: String,
    val telemetry: TelemetryData
)

data class TelemetryData(
    val probe_id: String = "PROBE-01",
    val crop_mode: String = "auto",
    val active_crop: String = "auto",
    val crop_name: String = "Auto-Detect",
    val farm_area: String = "Plot 1",
    val camera_active: Boolean = true,
    val camera_model: String = "FEELWORLD 4K10X 4K PTZ",
    val live_ai_enabled: Boolean = false,
    val latest_pest: String = "None",
    val latest_pest_count: Int = 0,
    val infestation_level: String = "None",
    val plant_health_status: String = "Healthy",
    val conf_threshold: Float = 0.25f,
    val box_thickness: Int = 2,
    val ptz: PtzStatus? = null,
    val recommendations: List<RecommendationItem>? = emptyList()
)

data class PtzStatus(
    val model_name: String = "FEELWORLD 4K10X 4K PTZ",
    val pan: Float = 0f,
    val tilt: Float = 0f,
    val zoom: Float = 1.0f,
    val zoom_display: String = "1.0x",
    val active_preset_id: Int? = 1,
    val patrol_mode: String = "off",
    val auto_zoom_on_detect: Boolean = true
)

data class PlantHealthDetails(
    val affected_part: String? = null,
    val primary_symptom: String? = null,
    val severity_level: String? = null,
    val visual_cues: String? = null
)

data class RecommendationItem(
    val status: String = "CONFIRMED",
    val is_beneficial: Boolean = false,
    val confidence: Float = 0.85f,
    val crop_type: String = "rice",
    val crop_name: String = "Rice / Paddy",
    val detected_pest: String = "None",
    val scientific_name: String? = "",
    val pest_count: Int = 0,
    val pest_count_for_species: Int? = 1,
    val max_confidence: Float? = null,
    val infestation_level: String = "None",
    val plant_health_status: String = "Healthy",
    val recommended_pesticide: String = "",
    val organic_alternative: String = "",
    val dosage_instruction: String = "",
    val safety_precautions: String = "",
    val pest_category: String? = null,
    val citation: String? = null,
    val plant_health_details: PlantHealthDetails? = null
)

data class PestImageryAssets(
    val reference_url: String,
    val svg_fallback_url: String,
    val has_photo: Boolean,
    val source: String,
    val latest_field_capture: FieldCaptureAsset? = null
)

data class FieldCaptureAsset(
    val url: String,
    val timestamp: String,
    val crop_type: String,
    val detected_pest: String
)

data class AdvisorResponse(
    val status: String,
    val recommendation: RecommendationItem,
    val images: PestImageryAssets? = null
)

data class UploadDetectionResponse(
    val status: String,
    val source: String,
    val crop_type: String,
    val crop_name: String,
    val pest_count: Int,
    val recommendation: RecommendationItem?,
    val recommendations: List<RecommendationItem>?,
    val plant_health: String,
    val record: DetectionRecord?,
    val image_url: String?,
    val crop_image_url: String?
)

data class DetectionRecord(
    val id: Int,
    val timestamp: String,
    val crop_type: String,
    val farm_area: String,
    val detected_pest: String,
    val pest_count: Int,
    val infestation_level: String,
    val plant_health_status: String,
    val confidence: Float,
    val recommended_pesticide: String,
    val organic_alternative: String,
    val dosage_instruction: String,
    val safety_precautions: String,
    val image_path: String,
    val crop_image_path: String? = ""
)

data class DetectionsListResponse(
    val status: String,
    val count: Int,
    val total: Int,
    val page: Int,
    val pages: Int,
    val detections: List<DetectionRecord>
)

data class CropSpeciesItem(
    val key: String,
    val common_name: String,
    val scientific_name: String
)

data class CropCatalogEntry(
    val key: String,
    val name: String,
    val pests: List<CropSpeciesItem>
)

data class CropsCatalogResponse(
    val status: String,
    val active_crop: String,
    val crops: List<CropCatalogEntry>
)

data class FarmStatsResponse(
    val status: String,
    val stats: FarmStatsData
)

data class FarmStatsData(
    val total_inspections: Int = 0,
    val severe_alerts: Int = 0,
    val pest_free_count: Int = 0,
    val beneficial_count: Int = 0,
    val harmful_pest_count: Int = 0,
    val most_common_pest: String = "None",
    val avg_confidence: Float = 0f,
    val top_pests: List<TopPestStat> = emptyList(),
    val crop_distribution: List<CropDistStat> = emptyList(),
    val severity_breakdown: Map<String, Int> = emptyMap()
)

data class TopPestStat(val detected_pest: String, val count: Int, val total_individuals: Int)
data class CropDistStat(val crop_type: String, val count: Int)

// Request Payloads
data class CropSelectRequest(val crop: String, val farm_area: String? = null)
data class LiveAiToggleRequest(val enabled: Boolean)
data class PtzMoveRequest(val action: String, val step: Float? = null, val zoom: Float? = null)
data class PtzPresetRequest(val action: String, val preset_id: Int, val name: String? = null)
data class PtzPatrolRequest(val patrol_mode: String? = null, val auto_zoom_on_detect: Boolean? = null)
data class BatchDeleteRequest(val ids: List<Int>)
data class ClearHistoryRequest(
    val password: String,
    val crop: String? = null,
    val infestation: String? = null,
    val search: String? = null
)

// ─── Retrofit Interface ─────────────────────────────────────────

interface AgriSentinelApi {

    @GET("/api/ping")
    suspend fun ping(): Response<PingResponse>

    @FormUrlEncoded
    @POST("/login")
    suspend fun login(
        @Field("username") username: String,
        @Field("password") password: String
    ): Response<ResponseBody>

    @GET("/api/status")
    suspend fun getStatus(): StatusResponse

    @GET("/api/crops")
    suspend fun getCropsCatalog(): CropsCatalogResponse

    @POST("/api/crop/select")
    suspend fun selectCrop(@Body req: CropSelectRequest): ResponseBody

    @POST("/api/vision/live_toggle")
    suspend fun toggleLiveAi(@Body req: LiveAiToggleRequest): ResponseBody

    @POST("/api/analyze")
    suspend fun triggerProbeAnalyze(@Body body: Map<String, String> = emptyMap()): UploadDetectionResponse

    @POST("/api/ptz/move")
    suspend fun movePtz(@Body req: PtzMoveRequest): ResponseBody

    @POST("/api/ptz/preset")
    suspend fun presetPtz(@Body req: PtzPresetRequest): ResponseBody

    @POST("/api/ptz/patrol")
    suspend fun patrolPtz(@Body req: PtzPatrolRequest): ResponseBody

    @Multipart
    @POST("/api/detect/upload")
    suspend fun uploadImageForDetection(
        @Part file: MultipartBody.Part,
        @Part("crop_type") cropType: RequestBody,
        @Part("conf_threshold") confThreshold: RequestBody,
        @Part("model_profile") modelProfile: RequestBody,
        @Part("source") source: RequestBody
    ): UploadDetectionResponse

    @GET("/api/recommendations/{crop}/{pest}")
    suspend fun getRecommendation(
        @Path("crop") crop: String,
        @Path("pest") pest: String,
        @Query("confidence") confidence: Float = 0.90f
    ): AdvisorResponse

    @GET("/api/detections")
    suspend fun getDetections(
        @Query("page") page: Int = 1,
        @Query("limit") limit: Int = 25,
        @Query("crop") crop: String = "all",
        @Query("infestation") infestation: String = "all",
        @Query("search") search: String = ""
    ): DetectionsListResponse

    @POST("/api/detections/batch_delete")
    suspend fun batchDeleteDetections(@Body req: BatchDeleteRequest): ResponseBody

    @POST("/api/detections/clear")
    suspend fun clearDetections(@Body req: ClearHistoryRequest): Response<ResponseBody>

    @GET("/api/stats")
    suspend fun getStats(): FarmStatsResponse
}
```

---

## 4. Network Client, Persistent Cookie Jar & mDNS Auto-Discovery (`ProbeClient.kt`)

Create `app/src/main/java/com/agrisentinel/mobile/network/ProbeClient.kt`:

```kotlin
package com.agrisentinel.mobile.network

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.*
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.TimeUnit

class PersistentCookieJar(context: Context) : CookieJar {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("agrisentinel_cookies", Context.MODE_PRIVATE)
    private val cookieStore = mutableMapOf<String, List<Cookie>>()

    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        cookieStore[url.host] = cookies
        cookies.find { it.name == "agrisentinel_session" }?.let {
            prefs.edit().putString("session_cookie", "${it.name}=${it.value}").apply()
        }
    }

    override fun loadForRequest(url: HttpUrl): List<Cookie> {
        val memCookies = cookieStore[url.host]
        if (!memCookies.isNullOrEmpty()) return memCookies

        val saved = prefs.getString("session_cookie", null) ?: return emptyList()
        val parts = saved.split("=", limit = 2)
        if (parts.size == 2) {
            val cookie = Cookie.Builder()
                .hostOnlyDomain(url.host)
                .name(parts[0])
                .value(parts[1])
                .path("/")
                .build()
            return listOf(cookie)
        }
        return emptyList()
    }

    fun getRawSessionCookie(): String? = prefs.getString("session_cookie", null)

    fun clear() {
        cookieStore.clear()
        prefs.edit().clear().apply()
    }
}

object ProbeClient {
    private var currentBaseUrl: String = "http://agrisentinel.local:8000"
    lateinit var cookieJar: PersistentCookieJar
    lateinit var okHttpClient: OkHttpClient
    lateinit var api: AgriSentinelApi

    fun init(context: Context) {
        val prefs = context.getSharedPreferences("agrisentinel_prefs", Context.MODE_PRIVATE)
        currentBaseUrl = prefs.getString("base_url", "http://agrisentinel.local:8000")!!
        cookieJar = PersistentCookieJar(context)
        rebuildClient(currentBaseUrl)
    }

    fun setBaseUrl(context: Context, newUrl: String) {
        val clean = newUrl.trim().removeSuffix("/")
        val formatted = if (clean.startsWith("http")) clean else "http://$clean"
        currentBaseUrl = formatted
        context.getSharedPreferences("agrisentinel_prefs", Context.MODE_PRIVATE)
            .edit().putString("base_url", formatted).apply()
        rebuildClient(formatted)
    }

    fun getBaseUrl(): String = currentBaseUrl

    fun resolveMediaUrl(relativePath: String?): String {
        if (relativePath.isNullOrBlank()) return ""
        if (relativePath.startsWith("http")) return relativePath
        val path = if (relativePath.startsWith("/")) relativePath else "/$relativePath"
        return "$currentBaseUrl$path"
    }

    private fun rebuildClient(baseUrl: String) {
        okHttpClient = OkHttpClient.Builder()
            .cookieJar(cookieJar)
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .writeTimeout(15, TimeUnit.SECONDS)
            .followRedirects(true)
            .build()

        api = Retrofit.Builder()
            .baseUrl("$baseUrl/")
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(AgriSentinelApi::class.java)
    }

    /**
     * Scans common probe endpoints (mDNS agrisentinel.local + Raspberry Pi AP Hotspot 192.168.4.1)
     */
    suspend fun autoDiscoverProbe(context: Context): String? = withContext(Dispatchers.IO) {
        val candidates = listOf(
            currentBaseUrl,
            "http://agrisentinel.local:8000",
            "http://192.168.4.1:8000"
        ).distinct()

        for (candidate in candidates) {
            try {
                val url = URL("$candidate/api/ping")
                val conn = (url.openConnection() as HttpURLConnection).apply {
                    connectTimeout = 1800
                    readTimeout = 1800
                    requestMethod = "GET"
                }
                if (conn.responseCode == 200) {
                    setBaseUrl(context, candidate)
                    return@withContext candidate
                }
            } catch (_: Exception) {
            }
        }
        return@withContext null
    }
}
```

---

## 5. Live 30 FPS MJPEG Stream Viewer Composable (`MjpegStreamView.kt`)

Standard Android `Image` or `VideoView` cannot natively decode `multipart/x-mixed-replace; boundary=frame` MJPEG streams from FastAPI `/video_feed`. This custom Composable decodes JPEG frames directly from the stream in real time:

```kotlin
package com.agrisentinel.mobile.ui.components

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.agrisentinel.mobile.network.ProbeClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import okhttp3.Request
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream

@Composable
fun MjpegStreamView(
    streamUrl: String,
    modifier: Modifier = Modifier
) {
    var currentFrame by remember { mutableStateOf<Bitmap?>(null) }
    var errorText by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(streamUrl) {
        errorText = null
        withContext(Dispatchers.IO) {
            while (isActive) {
                try {
                    val request = Request.Builder().url(streamUrl).build()
                    ProbeClient.okHttpClient.newCall(request).execute().use { response ->
                        if (!response.isSuccessful) {
                            errorText = "Stream offline (HTTP ${response.code})"
                            return@use
                        }
                        val input = BufferedInputStream(response.body?.byteStream() ?: return@use)
                        val buffer = ByteArrayOutputStream()
                        var prevByte = -1

                        while (isActive) {
                            val currByte = input.read()
                            if (currByte == -1) break

                            // Detect JPEG SOI (0xFF 0xD8)
                            if (prevByte == 0xFF && currByte == 0xD8) {
                                buffer.reset()
                                buffer.write(0xFF)
                                buffer.write(0xD8)
                            } else if (buffer.size() > 0) {
                                buffer.write(currByte)
                                // Detect JPEG EOI (0xFF 0xD9)
                                if (prevByte == 0xFF && currByte == 0xD9) {
                                    val jpegBytes = buffer.toByteArray()
                                    val bmp = BitmapFactory.decodeByteArray(jpegBytes, 0, jpegBytes.size)
                                    if (bmp != null) {
                                        currentFrame = bmp
                                        errorText = null
                                    }
                                    buffer.reset()
                                }
                            }
                            prevByte = currByte
                        }
                    }
                } catch (e: Exception) {
                    errorText = "Reconnecting to Probe camera..."
                    kotlinx.coroutines.delay(2000)
                }
            }
        }
    }

    Box(
        modifier = modifier.background(Color(0xFF090D16)),
        contentAlignment = Alignment.Center
    ) {
        val frame = currentFrame
        if (frame != null) {
            Image(
                bitmap = frame.asImageBitmap(),
                contentDescription = "Live Probe Stream",
                contentScale = ContentScale.Fit,
                modifier = Modifier.fillMaxSize()
            )
        } else {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                CircularProgressIndicator(color = Color(0xFF22C55E))
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = errorText ?: "Connecting to FEELWORLD 4K10X Stream...",
                    color = Color(0xFF94A3B8),
                    fontSize = 12.sp
                )
            }
        }
    }
}
```

---

## 6. WebSocket Real-Time Alert & Rich Push Notification Helper (`AlertWebSocketManager.kt`)

Create `app/src/main/java/com/agrisentinel/mobile/network/AlertWebSocketManager.kt`:

```kotlin
package com.agrisentinel.mobile.network

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.graphics.BitmapFactory
import android.media.RingtoneManager
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import okhttp3.*
import org.json.JSONObject
import java.net.URL

class AlertWebSocketManager(
    private val context: Context,
    private val onAlertReceived: (String, String) -> Unit
) {
    private var webSocket: WebSocket? = null
    private val channelId = "agrisentinel_pest_alerts"

    init {
        createNotificationChannel()
    }

    fun connect() {
        webSocket?.cancel()
        val wsUrl = ProbeClient.getBaseUrl()
            .replaceFirst("http://", "ws://")
            .replaceFirst("https://", "wss://") + "/ws/alerts"

        val request = Request.Builder().url(wsUrl).build()
        webSocket = ProbeClient.okHttpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    if (json.optString("type") == "PEST_DETECTION_ALERT") {
                        val summary = json.optString("summary", "Pest Detected on Crop")
                        val record = json.optJSONObject("record")
                        val pest = record?.optString("detected_pest", "Pest Alert") ?: "Pest Alert"
                        val severity = record?.optString("infestation_level", "Moderate") ?: "Moderate"
                        val cropImg = record?.optString("crop_image_path", "") ?: ""

                        onAlertReceived(pest, summary)
                        triggerNativeAlert(pest, summary, severity, cropImg)
                    }
                } catch (_: Exception) {
                }
            }
        })
    }

    private fun triggerNativeAlert(pest: String, summary: String, severity: String, cropImgPath: String) {
        // 1. Haptic Vibration
        val vibrator = context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        vibrator?.vibrate(VibrationEffect.createWaveform(longArrayOf(0, 250, 120, 350), -1))

        // 2. Sound Chime
        try {
            val toneUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
            RingtoneManager.getRingtone(context, toneUri)?.play()
        } catch (_: Exception) {}

        // 3. Rich Push Notification with Cropped Pest ROI Snapshot
        CoroutineScope(Dispatchers.IO).launch {
            val builder = NotificationCompat.Builder(context, channelId)
                .setSmallIcon(android.R.drawable.ic_dialog_alert)
                .setContentTitle("AgriSentinel [$severity]: $pest")
                .setContentText(summary)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)

            if (cropImgPath.isNotEmpty()) {
                try {
                    val fullUrl = ProbeClient.resolveMediaUrl(cropImgPath)
                    val bmp = BitmapFactory.decodeStream(URL(fullUrl).openStream())
                    if (bmp != null) {
                        builder.setLargeIcon(bmp)
                        builder.setStyle(
                            NotificationCompat.BigPictureStyle()
                                .bigPicture(bmp)
                                .setSummaryText(summary)
                        )
                    }
                } catch (_: Exception) {}
            }

            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.notify(System.currentTimeMillis().toInt(), builder.build())
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "AgriSentinel Pest Alerts",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Real-time crop pest detection alerts from AgriSentinel Probe"
            }
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(channel)
        }
    }

    fun disconnect() {
        webSocket?.close(1000, "App closed")
    }
}
```

---

## 7. Main Application & 4-Tab Compose Screens (`MainActivity.kt`)

Create `app/src/main/java/com/agrisentinel/mobile/MainActivity.kt`:

```kotlin
package com.agrisentinel.mobile

import android.Manifest
import android.content.Context
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import coil.ImageLoader
import coil.compose.AsyncImage
import coil.decode.SvgDecoder
import com.agrisentinel.mobile.network.*
import com.agrisentinel.mobile.ui.components.MjpegStreamView
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File

class MainActivity : ComponentActivity() {
    private var wsManager: AlertWebSocketManager? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ProbeClient.init(this)

        // Coil SVG support for taxonomic specimen cards
        val imageLoader = ImageLoader.Builder(this)
            .okHttpClient(ProbeClient.okHttpClient)
            .components { add(SvgDecoder.Factory()) }
            .build()
        coil.Coil.setImageLoader(imageLoader)

        setContent {
            val snackbarHostState = remember { SnackbarHostState() }
            val scope = rememberCoroutineScope()

            DisposableEffect(Unit) {
                wsManager = AlertWebSocketManager(this@MainActivity) { pest, summary ->
                    scope.launch {
                        snackbarHostState.showSnackbar("🚨 $pest: $summary")
                    }
                }.also { it.connect() }
                onDispose { wsManager?.disconnect() }
            }

            MaterialTheme(
                colorScheme = darkColorScheme(
                    primary = Color(0xFF22C55E),
                    secondary = Color(0xFF10B981),
                    background = Color(0xFF090D16),
                    surface = Color(0xFF131B2E)
                )
            ) {
                AgriSentinelApp(snackbarHostState)
            }
        }
    }
}

@Composable
fun AgriSentinelApp(snackbarHostState: SnackbarHostState) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var isAuthenticated by remember { mutableStateOf(ProbeClient.cookieJar.getRawSessionCookie() != null) }
    var currentTab by remember { mutableIntStateOf(0) }

    // Request Camera & Notification Permissions
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) {}
    LaunchedEffect(Unit) {
        permissionLauncher.launch(
            arrayOf(Manifest.permission.CAMERA, Manifest.permission.POST_NOTIFICATIONS)
        )
        ProbeClient.autoDiscoverProbe(context)
    }

    if (!isAuthenticated) {
        LoginScreen(onLoginSuccess = { isAuthenticated = true })
        return
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        bottomBar = {
            NavigationBar(containerColor = Color(0xFF0F172A)) {
                val tabs = listOf(
                    Triple(0, "Scout & PTZ", Icons.Default.Videocam),
                    Triple(1, "Advisor", Icons.Default.MedicalServices),
                    Triple(2, "History", Icons.Default.History),
                    Triple(3, "Analytics", Icons.Default.PieChart)
                )
                tabs.forEach { (idx, title, icon) ->
                    NavigationBarItem(
                        selected = currentTab == idx,
                        onClick = { currentTab = idx },
                        icon = { Icon(icon, contentDescription = title) },
                        label = { Text(title, fontSize = 11.sp) }
                    )
                }
            }
        }
    ) { padding ->
        Box(modifier = Modifier.padding(padding).fillMaxSize().background(Color(0xFF090D16))) {
            when (currentTab) {
                0 -> ScoutAndPtzScreen(onLogout = {
                    ProbeClient.cookieJar.clear()
                    isAuthenticated = false
                })
                1 -> PesticideAdvisorScreen()
                2 -> InspectionHistoryScreen()
                3 -> FarmAnalyticsScreen()
            }
        }
    }
}

// ─── 1. LOGIN & PROBE CONNECTION SCREEN ─────────────────────────

@Composable
fun LoginScreen(onLoginSuccess: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var hostInput by remember { mutableStateOf(ProbeClient.getBaseUrl()) }
    var username by remember { mutableStateOf("admin") }
    var password by remember { mutableStateOf("") }
    var statusMsg by remember { mutableStateOf<String?>(null) }
    var isLoading by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier.fillMaxSize().background(Color(0xFF090D16)).padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(Icons.Default.Eco, contentDescription = null, tint = Color(0xFF22C55E), modifier = Modifier.size(56.dp))
        Spacer(Modifier.height(8.dp))
        Text("AgriSentinel Mobile", color = Color.White, fontSize = 24.sp, fontWeight = FontWeight.Bold)
        Text("Smart Crop Probe & AI Pest Scout", color = Color(0xFF94A3B8), fontSize = 13.sp)
        Spacer(Modifier.height(24.dp))

        OutlinedTextField(
            value = hostInput,
            onValueChange = { hostInput = it },
            label = { Text("Probe Address (mDNS or IP)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = {
            scope.launch {
                statusMsg = "Scanning network for AgriSentinel Probe..."
                val found = ProbeClient.autoDiscoverProbe(context)
                if (found != null) {
                    hostInput = found
                    statusMsg = "Found Probe at $found"
                } else {
                    statusMsg = "Auto-discovery finished. Verify Wi-Fi or Hotspot IP."
                }
            }
        }) {
            Icon(Icons.Default.WifiFind, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
            Text("Auto-Discover Probe on Network")
        }

        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = username,
            onValueChange = { username = it },
            label = { Text("Username") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Password") },
            visualTransformation = PasswordVisualTransformation(),
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )

        if (statusMsg != null) {
            Spacer(Modifier.height(10.dp))
            Text(statusMsg!!, color = Color(0xFFF59E0B), fontSize = 12.sp)
        }

        Spacer(Modifier.height(20.dp))
        Button(
            onClick = {
                scope.launch {
                    isLoading = true
                    statusMsg = null
                    try {
                        ProbeClient.setBaseUrl(context, hostInput)
                        val res = ProbeClient.api.login(username, password)
                        if (res.isSuccessful) {
                            onLoginSuccess()
                        } else {
                            statusMsg = "Invalid credentials (HTTP ${res.code()})"
                        }
                    } catch (e: Exception) {
                        statusMsg = "Connection failed: ${e.localizedMessage}"
                    } finally {
                        isLoading = false
                    }
                }
            },
            enabled = !isLoading,
            modifier = Modifier.fillMaxWidth().height(50.dp)
        ) {
            Text(if (isLoading) "Connecting..." else "Connect & Sign In", fontWeight = FontWeight.Bold)
        }
    }
}

// ─── 2. TAB 1: SCOUT & PTZ SCREEN ───────────────────────────────

@Composable
fun ScoutAndPtzScreen(onLogout: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var telemetry by remember { mutableStateOf(TelemetryData()) }
    var isPhoneMode by remember { mutableStateOf(false) }
    var selectedCrop by remember { mutableStateOf("auto") }
    var selectedProfile by remember { mutableStateOf("comprehensive_102") }
    var confThreshold by remember { mutableFloatStateOf(0.25f) }

    // Latest analysis result (from either Probe capture or Phone upload)
    var fullSnapUrl by remember { mutableStateOf<String?>(null) }
    var cropSnapUrl by remember { mutableStateOf<String?>(null) }
    var recommendations by remember { mutableStateOf<List<RecommendationItem>>(emptyList()) }
    var selectedRecIndex by remember { mutableIntStateOf(0) }
    var isAnalyzing by remember { mutableStateOf(false) }

    // Poll telemetry every 3 seconds
    LaunchedEffect(Unit) {
        while (true) {
            try {
                val res = ProbeClient.api.getStatus()
                telemetry = res.telemetry
                if (recommendations.isEmpty() && !res.telemetry.recommendations.isNullOrEmpty()) {
                    recommendations = res.telemetry.recommendations
                }
            } catch (_: Exception) {}
            delay(3000)
        }
    }

    // Helper to upload image file from Phone Camera or Gallery
    fun uploadFileForDiagnosis(file: File) {
        scope.launch {
            isAnalyzing = true
            try {
                val reqFile = file.asRequestBody("image/jpeg".toMediaTypeOrNull())
                val body = MultipartBody.Part.createFormData("file", file.name, reqFile)
                val res = ProbeClient.api.uploadImageForDetection(
                    file = body,
                    cropType = selectedCrop.toRequestBody(),
                    confThreshold = confThreshold.toString().toRequestBody(),
                    modelProfile = selectedProfile.toRequestBody(),
                    source = "phone_camera".toRequestBody()
                )
                fullSnapUrl = ProbeClient.resolveMediaUrl(res.image_url)
                cropSnapUrl = ProbeClient.resolveMediaUrl(res.crop_image_url)
                recommendations = res.recommendations ?: listOfNotNull(res.recommendation)
                selectedRecIndex = 0
            } catch (_: Exception) {
            } finally {
                isAnalyzing = false
            }
        }
    }

    // Native Gallery Picker
    val galleryLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        if (uri != null) {
            val tempFile = File(context.cacheDir, "upload_${System.currentTimeMillis()}.jpg")
            context.contentResolver.openInputStream(uri)?.use { input ->
                tempFile.outputStream().use { output -> input.copyTo(output) }
            }
            uploadFileForDiagnosis(tempFile)
        }
    }

    // Native Phone Camera Capture
    var tempPhotoFile by remember { mutableStateOf<File?>(null) }
    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { success: Boolean ->
        if (success && tempPhotoFile != null) {
            uploadFileForDiagnosis(tempPhotoFile!!)
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Header Row
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text("AgriSentinel Scout", color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                Text(
                    "${telemetry.camera_model} • ${telemetry.crop_name}",
                    color = Color(0xFF4ADE80),
                    fontSize = 11.sp
                )
            }
            IconButton(onClick = onLogout) {
                Icon(Icons.Default.Logout, contentDescription = "Logout", tint = Color(0xFF94A3B8))
            }
        }

        // Mode Switcher: Probe Stream vs Phone Camera
        Row(
            modifier = Modifier.fillMaxWidth().background(Color(0xFF131B2E), RoundedCornerShape(12.dp)).padding(4.dp)
        ) {
            Button(
                onClick = { isPhoneMode = false },
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (!isPhoneMode) Color(0xFF22C55E) else Color.Transparent
                ),
                modifier = Modifier.weight(1f)
            ) {
                Text("Probe Camera + PTZ", fontSize = 12.sp, color = Color.White)
            }
            Button(
                onClick = { isPhoneMode = true },
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isPhoneMode) Color(0xFF22C55E) else Color.Transparent
                ),
                modifier = Modifier.weight(1f)
            ) {
                Text("Phone Camera / Upload", fontSize = 12.sp, color = Color.White)
            }
        }

        // Crop Quick Chips
        val crops = listOf(
            "auto" to "🔥 Auto-Detect",
            "rice" to "🌾 Rice",
            "corn" to "🌽 Corn",
            "wheat" to "🌿 Wheat",
            "citrus" to "🍊 Citrus",
            "mango" to "🥭 Mango"
        )
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(crops) { (key, label) ->
                FilterChip(
                    selected = selectedCrop == key,
                    onClick = {
                        selectedCrop = key
                        scope.launch {
                            try { ProbeClient.api.selectCrop(CropSelectRequest(key)) } catch (_: Exception) {}
                        }
                    },
                    label = { Text(label, fontSize = 11.sp) }
                )
            }
        }

        if (!isPhoneMode) {
            // ── PROBE STREAM & FEELWORLD 4K10X PTZ MODE ──
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(16f / 9f)
                    .clip(RoundedCornerShape(14.dp))
                    .border(1.dp, Color(0xFF334155), RoundedCornerShape(14.dp))
            ) {
                MjpegStreamView(
                    streamUrl = "${ProbeClient.getBaseUrl()}/video_feed",
                    modifier = Modifier.fillMaxSize()
                )
                Surface(
                    color = Color(0xAA0F172A),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.align(Alignment.TopEnd).padding(8.dp)
                ) {
                    Text(
                        text = "Pan: ${telemetry.ptz?.pan ?: 0f}° · Tilt: ${telemetry.ptz?.tilt ?: 0f}° · ${telemetry.ptz?.zoom_display ?: "1.0x"}",
                        color = Color.White,
                        fontSize = 10.sp,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            // Probe Action Buttons
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                Button(
                    onClick = {
                        scope.launch {
                            isAnalyzing = true
                            try {
                                val res = ProbeClient.api.triggerProbeAnalyze()
                                res.record?.let { rec ->
                                    fullSnapUrl = ProbeClient.resolveMediaUrl(rec.image_path)
                                    cropSnapUrl = ProbeClient.resolveMediaUrl(rec.crop_image_path)
                                }
                            } catch (_: Exception) {}
                            isAnalyzing = false
                        }
                    },
                    modifier = Modifier.weight(1f)
                ) {
                    Icon(Icons.Default.Camera, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(if (isAnalyzing) "Analyzing..." else "Capture & Inspect", fontSize = 12.sp)
                }

                OutlinedButton(
                    onClick = {
                        scope.launch {
                            try {
                                ProbeClient.api.toggleLiveAi(LiveAiToggleRequest(!telemetry.live_ai_enabled))
                            } catch (_: Exception) {}
                        }
                    },
                    modifier = Modifier.weight(1f)
                ) {
                    Text(
                        if (telemetry.live_ai_enabled) "Live AI: ON" else "Live AI: OFF (30 FPS)",
                        fontSize = 12.sp,
                        color = if (telemetry.live_ai_enabled) Color(0xFF4ADE80) else Color(0xFF94A3B8)
                    )
                }
            }

            // FEELWORLD 4K10X PTZ Control Card
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFF131B2E)),
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("FEELWORLD 4K10X 10X Optical PTZ Controls", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceEvenly
                    ) {
                        OutlinedButton(onClick = { scope.launch { try { ProbeClient.api.movePtz(PtzMoveRequest("pan_left")) } catch (_: Exception) {} } }) { Text("◀ Left") }
                        OutlinedButton(onClick = { scope.launch { try { ProbeClient.api.movePtz(PtzMoveRequest("tilt_up")) } catch (_: Exception) {} } }) { Text("▲ Up") }
                        OutlinedButton(onClick = { scope.launch { try { ProbeClient.api.movePtz(PtzMoveRequest("home")) } catch (_: Exception) {} } }) { Text("⌂ Home") }
                        OutlinedButton(onClick = { scope.launch { try { ProbeClient.api.movePtz(PtzMoveRequest("tilt_down")) } catch (_: Exception) {} } }) { Text("▼ Down") }
                        OutlinedButton(onClick = { scope.launch { try { ProbeClient.api.movePtz(PtzMoveRequest("pan_right")) } catch (_: Exception) {} } }) { Text("Right ▶") }
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceEvenly
                    ) {
                        listOf(1 to "P1 Center", 2 to "P2 Left", 3 to "P3 Right", 4 to "P4 Upper").forEach { (id, name) ->
                            AssistChip(
                                onClick = { scope.launch { try { ProbeClient.api.presetPtz(PtzPresetRequest("recall", id)) } catch (_: Exception) {} } },
                                label = { Text(name, fontSize = 10.sp) }
                            )
                        }
                    }
                }
            }
        } else {
            // ── PHONE CAMERA & GALLERY UPLOAD MODE ──
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFF131B2E)),
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Phone Field Scouting (Instant AI Diagnosis)", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                    Text(
                        "Snap a leaf/stem photo with your phone camera or pick an image from storage. Automatically generates both uncropped and 480x480 cropped pest ROI snapshots.",
                        color = Color(0xFF94A3B8),
                        fontSize = 12.sp
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                        Button(
                            onClick = {
                                val file = File(context.cacheDir, "snap_${System.currentTimeMillis()}.jpg")
                                tempPhotoFile = file
                                val uri = FileProvider.getUriForFile(context, "${context.packageName}.provider", file)
                                cameraLauncher.launch(uri)
                            },
                            modifier = Modifier.weight(1f)
                        ) {
                            Icon(Icons.Default.PhotoCamera, contentDescription = null)
                            Spacer(Modifier.width(6.dp))
                            Text("Snap Photo")
                        }
                        OutlinedButton(
                            onClick = { galleryLauncher.launch("image/*") },
                            modifier = Modifier.weight(1f)
                        ) {
                            Icon(Icons.Default.UploadFile, contentDescription = null)
                            Spacer(Modifier.width(6.dp))
                            Text("Choose Image")
                        }
                    }
                }
            }
        }

        // ── DUAL SNAPSHOT PREVIEW (Uncropped Full + Cropped Pest ROI) ──
        if (!fullSnapUrl.isNullOrEmpty() || !cropSnapUrl.isNullOrEmpty()) {
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFF131B2E)),
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Captured Dual Inspection Snapshots", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("1. Uncropped Full Scene", color = Color(0xFF94A3B8), fontSize = 10.sp)
                            AsyncImage(
                                model = fullSnapUrl,
                                contentDescription = "Full Snapshot",
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.fillMaxWidth().height(130.dp).clip(RoundedCornerShape(8.dp))
                            )
                        }
                        Column(modifier = Modifier.weight(1f)) {
                            Text("2. Cropped Pest ROI Macro", color = Color(0xFF4ADE80), fontSize = 10.sp)
                            AsyncImage(
                                model = cropSnapUrl,
                                contentDescription = "Cropped Pest ROI",
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.fillMaxWidth().height(130.dp).clip(RoundedCornerShape(8.dp))
                            )
                        }
                    }
                }
            }
        }

        // ── MULTI-PEST RECOMMENDATIONS CARD (#recSection equivalent) ──
        if (recommendations.isNotEmpty()) {
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFF131B2E)),
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Agronomic & Pesticide Recommendations", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp)

                    if (recommendations.size > 1) {
                        LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            items(recommendations.indices.toList()) { idx ->
                                val r = recommendations[idx]
                                FilterChip(
                                    selected = selectedRecIndex == idx,
                                    onClick = { selectedRecIndex = idx },
                                    label = {
                                        Text("${r.detected_pest} ×${r.pest_count_for_species ?: 1}", fontSize = 11.sp)
                                    }
                                )
                            }
                        }
                    }

                    val activeRec = recommendations.getOrElse(selectedRecIndex) { recommendations.first() }
                    Text(
                        "${activeRec.detected_pest} (${activeRec.scientific_name ?: ""})",
                        color = Color(0xFF4ADE80),
                        fontWeight = FontWeight.Bold,
                        fontSize = 15.sp
                    )
                    Text("Plant Health: ${activeRec.plant_health_status} • Severity: ${activeRec.infestation_level}", color = Color(0xFFE2E8F0), fontSize = 12.sp)

                    HorizontalDivider(color = Color(0xFF1E293B))
                    Text("Chemical Control: ${activeRec.recommended_pesticide}", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    Text("Dosage & PHI: ${activeRec.dosage_instruction}", color = Color(0xFFCBD5E1), fontSize = 12.sp)
                    Text("Organic / Biocontrol: ${activeRec.organic_alternative}", color = Color(0xFF34D399), fontSize = 12.sp)
                    Text("Safety & PPE: ${activeRec.safety_precautions}", color = Color(0xFFFCA5A5), fontSize = 11.sp)
                }
            }
        }
    }
}

// ─── 3. TAB 2: PESTICIDE ADVISOR WITH PEST SPECIMEN IMAGES ──────

@Composable
fun PesticideAdvisorScreen() {
    val scope = rememberCoroutineScope()
    var crops by remember { mutableStateOf<List<CropCatalogEntry>>(emptyList()) }
    var selectedCrop by remember { mutableStateOf<CropCatalogEntry?>(null) }
    var selectedPest by remember { mutableStateOf<CropSpeciesItem?>(null) }
    var advisorData by remember { mutableStateOf<AdvisorResponse?>(null) }

    LaunchedEffect(Unit) {
        try {
            val res = ProbeClient.api.getCropsCatalog()
            crops = res.crops
            selectedCrop = res.crops.firstOrNull()
            selectedPest = selectedCrop?.pests?.firstOrNull()
        } catch (_: Exception) {}
    }

    LaunchedEffect(selectedCrop, selectedPest) {
        val c = selectedCrop?.key ?: return@LaunchedEffect
        val p = selectedPest?.key ?: return@LaunchedEffect
        try {
            advisorData = ProbeClient.api.getRecommendation(c, p)
        } catch (_: Exception) {}
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Multi-Crop Pesticide Advisor", color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)

        // Crop Selector
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(crops) { crop ->
                FilterChip(
                    selected = selectedCrop?.key == crop.key,
                    onClick = {
                        selectedCrop = crop
                        selectedPest = crop.pests.firstOrNull()
                    },
                    label = { Text(crop.name, fontSize = 12.sp) }
                )
            }
        }

        // Pest Species Selector (20 IP102 species per crop)
        selectedCrop?.let { crop ->
            LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                items(crop.pests) { pest ->
                    FilterChip(
                        selected = selectedPest?.key == pest.key,
                        onClick = { selectedPest = pest },
                        label = { Text(pest.common_name, fontSize = 11.sp) }
                    )
                }
            }
        }

        advisorData?.let { data ->
            val rec = data.recommendation
            Card(
                colors = CardDefaults.cardColors(containerColor = Color(0xFF131B2E)),
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    // Side-by-Side Reference Specimen Image + Latest Field Capture
                    data.images?.let { imgs ->
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text("Reference Specimen", color = Color(0xFF4ADE80), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                AsyncImage(
                                    model = ProbeClient.resolveMediaUrl(imgs.reference_url),
                                    contentDescription = rec.detected_pest,
                                    contentScale = ContentScale.Fit,
                                    modifier = Modifier.fillMaxWidth().height(150.dp).clip(RoundedCornerShape(8.dp)).background(Color(0xFF0F172A))
                                )
                            }
                            Column(modifier = Modifier.weight(1f)) {
                                Text("Latest Farm Capture", color = Color(0xFFF59E0B), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                if (imgs.latest_field_capture != null) {
                                    AsyncImage(
                                        model = ProbeClient.resolveMediaUrl(imgs.latest_field_capture.url),
                                        contentDescription = "Field Capture",
                                        contentScale = ContentScale.Crop,
                                        modifier = Modifier.fillMaxWidth().height(150.dp).clip(RoundedCornerShape(8.dp))
                                    )
                                } else {
                                    Box(
                                        modifier = Modifier.fillMaxWidth().height(150.dp).clip(RoundedCornerShape(8.dp)).background(Color(0xFF0F172A)),
                                        contentAlignment = Alignment.Center
                                    ) {
                                        Text("No farm capture yet", color = Color(0xFF64748B), fontSize = 11.sp)
                                    }
                                }
                            }
                        }
                    }

                    Text("${rec.detected_pest} (${rec.scientific_name ?: ""})", color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.Bold)

                    rec.plant_health_details?.let { d ->
                        Surface(color = Color(0xFF0F172A), shape = RoundedCornerShape(8.dp), modifier = Modifier.fillMaxWidth()) {
                            Column(modifier = Modifier.padding(10.dp)) {
                                Text("Symptoms & Diagnostic Cues", color = Color(0xFF4ADE80), fontSize = 12.sp, fontWeight = FontWeight.Bold)
                                Text("Affected Part: ${d.affected_part ?: "-"}", color = Color(0xFFCBD5E1), fontSize = 11.sp)
                                Text("Symptom: ${d.primary_symptom ?: "-"}", color = Color(0xFFCBD5E1), fontSize = 11.sp)
                                Text("Visual Cues: ${d.visual_cues ?: "-"}", color = Color(0xFF94A3B8), fontSize = 11.sp)
                            }
                        }
                    }

                    Text("Chemical Pesticide: ${rec.recommended_pesticide}", color = Color(0xFF4ADE80), fontSize = 13.sp, fontWeight = FontWeight.Bold)
                    Text("Application Rate & PHI: ${rec.dosage_instruction}", color = Color.White, fontSize = 12.sp)
                    Text("Organic / Biocontrol: ${rec.organic_alternative}", color = Color(0xFF34D399), fontSize = 12.sp)
                    Text("Safety & PPE: ${rec.safety_precautions}", color = Color(0xFFFCA5A5), fontSize = 11.sp)
                    rec.citation?.let {
                        Text("Source: $it", color = Color(0xFF64748B), fontSize = 10.sp, fontStyle = FontStyle.Italic)
                    }
                }
            }
        }
    }
}

// ─── 4. TAB 3: INSPECTION HISTORY & PASSWORD WIPE ───────────────

@Composable
fun InspectionHistoryScreen() {
    val scope = rememberCoroutineScope()
    var records by remember { mutableStateOf<List<DetectionRecord>>(emptyList()) }
    var showClearDialog by remember { mutableStateOf(false) }
    var clearPassword by remember { mutableStateOf("") }
    var clearError by remember { mutableStateOf<String?>(null) }

    fun loadHistory() {
        scope.launch {
            try {
                val res = ProbeClient.api.getDetections()
                records = res.detections
            } catch (_: Exception) {}
        }
    }

    LaunchedEffect(Unit) { loadHistory() }

    Column(modifier = Modifier.fillMaxSize().padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Inspection History", color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)
            OutlinedButton(onClick = { showClearDialog = true }) {
                Icon(Icons.Default.DeleteForever, contentDescription = null, tint = Color(0xFFEF4444))
                Spacer(Modifier.width(4.dp))
                Text("Clear History", color = Color(0xFFEF4444), fontSize = 12.sp)
            }
        }

        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(records) { rec ->
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color(0xFF131B2E)),
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(modifier = Modifier.padding(10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        // Dual Thumbnails (Full + Cropped ROI)
                        AsyncImage(
                            model = ProbeClient.resolveMediaUrl(rec.image_path),
                            contentDescription = "Full",
                            contentScale = ContentScale.Crop,
                            modifier = Modifier.size(64.dp).clip(RoundedCornerShape(6.dp))
                        )
                        if (!rec.crop_image_path.isNullOrEmpty()) {
                            AsyncImage(
                                model = ProbeClient.resolveMediaUrl(rec.crop_image_path),
                                contentDescription = "ROI Crop",
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.size(64.dp).clip(RoundedCornerShape(6.dp)).border(1.5.dp, Color(0xFF22C55E), RoundedCornerShape(6.dp))
                            )
                        }
                        Column(modifier = Modifier.weight(1f)) {
                            Text(rec.detected_pest, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                            Text("${rec.crop_type.uppercase()} • ${rec.infestation_level} • ${(rec.confidence * 100).toInt()}%", color = Color(0xFF4ADE80), fontSize = 11.sp)
                            Text(rec.plant_health_status, color = Color(0xFF94A3B8), fontSize = 11.sp)
                            Text(rec.timestamp.take(19).replace("T", " "), color = Color(0xFF64748B), fontSize = 10.sp)
                        }
                    }
                }
            }
        }
    }

    if (showClearDialog) {
        AlertDialog(
            onDismissRequest = { showClearDialog = false; clearError = null },
            title = { Text("Confirm History Wipe") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Enter your account password to permanently wipe all inspection records and snapshots:")
                    OutlinedTextField(
                        value = clearPassword,
                        onValueChange = { clearPassword = it },
                        label = { Text("Account Password") },
                        visualTransformation = PasswordVisualTransformation(),
                        singleLine = true
                    )
                    if (clearError != null) {
                        Text(clearError!!, color = Color(0xFFEF4444), fontSize = 12.sp)
                    }
                }
            },
            confirmButton = {
                Button(onClick = {
                    scope.launch {
                        val res = ProbeClient.api.clearDetections(ClearHistoryRequest(password = clearPassword))
                        if (res.isSuccessful) {
                            showClearDialog = false
                            clearPassword = ""
                            clearError = null
                            loadHistory()
                        } else {
                            clearError = "Incorrect password. Authorization required."
                        }
                    }
                }) {
                    Text("Verify & Wipe")
                }
            },
            dismissButton = {
                TextButton(onClick = { showClearDialog = false }) { Text("Cancel") }
            }
        )
    }
}

// ─── 5. TAB 4: DATABASE-DRIVEN FARM ANALYTICS ───────────────────

@Composable
fun FarmAnalyticsScreen() {
    var stats by remember { mutableStateOf(FarmStatsData()) }

    LaunchedEffect(Unit) {
        try {
            stats = ProbeClient.api.getStats().stats
        } catch (_: Exception) {}
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Farm Analytics (Live SQLite DB)", color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            KpiCard("Total Inspections", stats.total_inspections.toString(), Color(0xFF38BDF8), Modifier.weight(1f))
            KpiCard("Severe Alerts", stats.severe_alerts.toString(), Color(0xFFEF4444), Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            KpiCard("Harmful Pests", stats.harmful_pest_count.toString(), Color(0xFFF59E0B), Modifier.weight(1f))
            KpiCard("Beneficial / Clean", (stats.beneficial_count + stats.pest_free_count).toString(), Color(0xFF22C55E), Modifier.weight(1f))
        }

        Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF131B2E)), modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Top Detected Pests", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                stats.top_pests.forEach { p ->
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(p.detected_pest, color = Color(0xFFE2E8F0), fontSize = 12.sp)
                        Text("${p.count} detections", color = Color(0xFF4ADE80), fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }

        Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF131B2E)), modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Inspections by Crop", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                stats.crop_distribution.forEach { c ->
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(c.crop_type.uppercase(), color = Color(0xFFE2E8F0), fontSize = 12.sp)
                        Text("${c.count} records", color = Color(0xFF38BDF8), fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
fun KpiCard(label: String, value: String, color: Color, modifier: Modifier = Modifier) {
    Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF131B2E)), modifier = modifier) {
        Column(modifier = Modifier.padding(14.dp)) {
            Text(label, color = Color(0xFF94A3B8), fontSize = 11.sp)
            Spacer(Modifier.height(4.dp))
            Text(value, color = color, fontSize = 22.sp, fontWeight = FontWeight.ExtraBold)
        }
    }
}
```

