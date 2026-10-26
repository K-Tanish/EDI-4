package com.tourist.safety

import okhttp3.OkHttpClient
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.*
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

// ── Response models ────────────────────────────────────────────────────────
data class RegisterResponse(val status: String, val touristId: String, val validUntil: Long, val txHash: String?, val token: String?)
data class ZoneApiModel(val zoneId: String, val name: String, val type: String, val riskLevel: String,
                        val centerLat: Double, val centerLng: Double, val radiusMeters: Double, val active: Boolean)
data class ZonesResponse(val zones: List<ZoneApiModel>)
data class ScoreResponse(val touristId: String, val score: Int, val label: String)
data class SosResponse(val sosId: String, val status: String, val txHash: String?)

// ── Retrofit interface ─────────────────────────────────────────────────────
interface MaharashtraApi {
    @POST("api/v1/register")
    suspend fun register(@Body body: RegistrationRequest): Response<RegisterResponse>

    @POST("api/v1/location")
    suspend fun updateLocation(
        @Header("Authorization") token: String,
        @Body body: LocationPayload
    ): Response<Unit>

    @POST("api/v1/sos")
    suspend fun triggerSos(
        @Header("Authorization") token: String,
        @Body body: SosRequest
    ): Response<SosResponse>

    @GET("api/v1/zones")
    suspend fun getZones(): Response<ZonesResponse>

    @GET("api/v1/score/{touristId}")
    suspend fun getScore(
        @Path("touristId") touristId: String
    ): Response<ScoreResponse>
}

// ── Singleton client ───────────────────────────────────────────────────────
object ApiClient {
    // 10.0.2.2 = Android emulator loopback to host machine
    // For a REAL phone: change this to your PC's local IP, e.g. "http://192.168.1.5:8000/"
    // Find your IP with: ipconfig (Windows) or ifconfig (Mac/Linux)
    private const val BASE_URL = "http://192.168.31.93:8000/"

    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    val api: MaharashtraApi = Retrofit.Builder()
        .baseUrl(BASE_URL)
        .client(http)
        .addConverterFactory(GsonConverterFactory.create())
        .build()
        .create(MaharashtraApi::class.java)

    suspend fun getZones() = api.getZones()

    /** Quick reachability check — returns true if backend /health responds OK */
    suspend fun isReachable(): Pair<Boolean, String> {
        return try {
            val client = okhttp3.OkHttpClient.Builder()
                .connectTimeout(5, TimeUnit.SECONDS)
                .readTimeout(5, TimeUnit.SECONDS)
                .build()
            val req = okhttp3.Request.Builder().url("${BASE_URL}health").build()
            val resp = withContext(kotlinx.coroutines.Dispatchers.IO) { client.newCall(req).execute() }
            Pair(resp.isSuccessful, "HTTP ${resp.code}")
        } catch (e: Exception) {
            Pair(false, e.message ?: "Unknown error")
        }
    }
}
