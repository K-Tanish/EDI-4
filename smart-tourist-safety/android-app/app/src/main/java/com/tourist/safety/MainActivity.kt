package com.tourist.safety

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.google.android.gms.location.LocationServices
import com.tourist.safety.databinding.ActivityMainBinding
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * MainActivity — home screen for Maharashtra Tourist Safety app.
 * Shows Digital_Tourist_ID, safety score, SOS button, tracking toggle.
 * Implements: Requirements 2.1, 5.3, 6.1, 6.2
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private var touristId: String = ""
    private val PERM_CODE = 100
    private val demoSimulator = DemoSimulator()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Check for existing valid Digital_Tourist_ID
        touristId = TouristPreferences.getTouristId(this) ?: ""
        if (touristId.isEmpty()) {
            showRegistrationPrompt()
        } else {
            displayTouristId()
            startSafetyScorePolling()
        }

        setupButtons()
        if (!hasLocationPerm()) requestPerms()

        // Refresh zones from backend
        lifecycleScope.launch {
            GeofenceManager.refreshZones(ApiClient)
        }
    }

    private fun displayTouristId() {
        val name = TouristPreferences.getName(this)
        binding.tvName.text = if (!name.isNullOrEmpty()) "Welcome, $name" else ""
        binding.tvTouristId.text = "ID: $touristId"
        val validUntil = TouristPreferences.getValidUntil(this)
        if (validUntil > 0) {
            val date = java.text.SimpleDateFormat("dd MMM yyyy", java.util.Locale.getDefault())
                .format(java.util.Date(validUntil))
            binding.tvStatus.text = "Valid until: $date"
        }
        FirebaseRepository.registerTourist(touristId, TouristPreferences.getName(this))
    }

    private fun showRegistrationPrompt() {
        binding.tvTouristId.text = "No Digital Tourist ID"
        binding.tvStatus.text = "Please register to get your ID"
        RegistrationDialog(this) { touristId, validUntil, txHash ->
            this.touristId = touristId
            TouristPreferences.saveTouristRecord(this, touristId, validUntil, txHash)
            displayTouristId()
            startSafetyScorePolling()
        }.show()
    }

    private fun startSafetyScorePolling() {
        lifecycleScope.launch {
            while (true) {
                delay(30_000L)
                refreshSafetyScore()
            }
        }
        // Initial fetch
        lifecycleScope.launch { refreshSafetyScore() }
    }

    private suspend fun refreshSafetyScore() {
        if (touristId.isEmpty()) return
        try {
            val resp = ApiClient.api.getScore(touristId)
            if (resp.isSuccessful) {
                resp.body()?.let { score ->
                    runOnUiThread { updateScoreDisplay(score.score, score.label) }
                }
            }
        } catch (e: Exception) {
            // Silently fail — score will refresh on next poll
        }
    }

    private fun updateScoreDisplay(score: Int, label: String) {
        binding.tvStatus.text = "Safety Score: $score — $label"
        setStatus(label)
    }

    private fun setupButtons() {
        binding.btnTracking.setOnClickListener {
            if (LocationTrackingService.isRunning) stopTracking()
            else if (hasLocationPerm()) startTracking() else requestPerms()
        }

        binding.btnTestConnection.setOnClickListener {
            lifecycleScope.launch {
                binding.btnTestConnection.isEnabled = false
                binding.btnTestConnection.text = "Testing…"
                val (ok, msg) = ApiClient.isReachable()
                val result = if (ok) "Backend OK: $msg" else "FAILED: $msg"
                Toast.makeText(this@MainActivity, result, Toast.LENGTH_LONG).show()
                android.util.Log.d("ConnectionTest", result)
                binding.btnTestConnection.text = "Test Backend Connection"
                binding.btnTestConnection.isEnabled = true
            }
        }

        binding.btnDemo.setOnClickListener {
            if (demoSimulator.isRunning()) {
                demoSimulator.stop()
                binding.btnDemo.text = "Start Demo Mode"
                Toast.makeText(this, "Demo stopped", Toast.LENGTH_SHORT).show()
            } else {
                demoSimulator.start(lifecycleScope)
                binding.btnDemo.text = "Stop Demo Mode"
                Toast.makeText(this, "Demo started — 5 tourists simulated on map", Toast.LENGTH_LONG).show()
            }
        }

        binding.btnSos.setOnClickListener {
            if (!hasLocationPerm()) { requestPerms(); return@setOnClickListener }
            if (ActivityCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED) return@setOnClickListener

            LocationServices.getFusedLocationProviderClient(this).lastLocation
                .addOnSuccessListener { loc ->
                    val lat = loc?.latitude ?: 0.0
                    val lng = loc?.longitude ?: 0.0
                    lifecycleScope.launch { sendSos(lat, lng) }
                }
                .addOnFailureListener {
                    lifecycleScope.launch { sendSos(0.0, 0.0) }
                }
        }
    }

    private suspend fun sendSos(lat: Double, lng: Double) {
        // Firebase SOS (works offline)
        FirebaseRepository.sendSos(touristId, lat, lng)

        // Backend API SOS
        val jwt = TouristPreferences.getJwt(this)
        if (jwt != null) {
            try {
                ApiClient.api.triggerSos("Bearer $jwt", SosRequest(touristId, lat, lng))
            } catch (e: Exception) {
                // Queued offline — Firebase already has it
            }
        }

        // Switch to 3s tracking interval
        startService(Intent(this, LocationTrackingService::class.java).apply {
            action = LocationTrackingService.ACTION_SOS_MODE
        })

        runOnUiThread {
            binding.tvStatus.text = "SOS SENT — Help is on the way"
            setStatus("SOS")
            Toast.makeText(this, "SOS Alert Sent!", Toast.LENGTH_LONG).show()
        }
    }

    private fun startTracking() {
        ContextCompat.startForegroundService(this,
            Intent(this, LocationTrackingService::class.java)
                .putExtra("touristId", touristId)
                .putExtra("intervalMs", LocationTrackingService.NORMAL_INTERVAL_MS))
        binding.btnTracking.text = "Stop Tracking"
        val name = TouristPreferences.getName(this)
        binding.tvStatus.text = if (!name.isNullOrEmpty()) "Tracking: $name" else "Tracking active"
        setStatus("SAFE")
    }

    private fun stopTracking() {
        startService(Intent(this, LocationTrackingService::class.java)
            .apply { action = LocationTrackingService.ACTION_STOP })
        binding.btnTracking.text = "Start Tracking"
        binding.tvStatus.text = "Tracking stopped"
        setStatus("OFFLINE")
    }

    private fun setStatus(status: String) {
        val color = when (status) {
            "SAFE"    -> 0xFF00C853.toInt()
            "CAUTION" -> 0xFFFF6D00.toInt()
            "DANGER"  -> 0xFFD50000.toInt()
            "SOS"     -> 0xFFD50000.toInt()
            else      -> 0xFF757575.toInt()
        }
        binding.statusIndicator.setBackgroundColor(color)
        binding.tvStatusLabel.text = status
    }

    private fun hasLocationPerm() = ContextCompat.checkSelfPermission(
        this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED

    private fun requestPerms() = ActivityCompat.requestPermissions(this,
        arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION), PERM_CODE)

    override fun onRequestPermissionsResult(code: Int, perms: Array<String>, results: IntArray) {
        super.onRequestPermissionsResult(code, perms, results)
        if (code == PERM_CODE && results.isNotEmpty() && results[0] == PackageManager.PERMISSION_GRANTED)
            Toast.makeText(this, "Location permission granted", Toast.LENGTH_SHORT).show()
        else
            Toast.makeText(this, "Location permission required for safety features", Toast.LENGTH_LONG).show()
    }
}
