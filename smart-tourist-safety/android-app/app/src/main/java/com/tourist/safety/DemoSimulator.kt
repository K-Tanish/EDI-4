package com.tourist.safety

import kotlinx.coroutines.*
import kotlin.random.Random

/**
 * DemoSimulator - simulates 5 tourists for dashboard testing.
 * Generates realistic movement and occasionally triggers SOS/geofence alerts.
 */
class DemoSimulator {
    private var job: Job? = null

    private val tourists = listOf(
        Triple("DEMO_TOURIST_001", doubleArrayOf(19.0760, 72.8777), "Mumbai Urban Core"),
        Triple("DEMO_TOURIST_002", doubleArrayOf(18.5204, 73.8567), "Pune Urban Core"),
        Triple("DEMO_TOURIST_003", doubleArrayOf(20.5519, 75.7033), "Ajanta Caves"),
        Triple("DEMO_TOURIST_004", doubleArrayOf(20.2280, 79.3950), "Tadoba Tiger Reserve"),
        Triple("DEMO_TOURIST_005", doubleArrayOf(17.0000, 73.2500), "Konkan Coastal Belt")
    )

    fun start(scope: CoroutineScope, intervalMs: Long = 3000L) {
        tourists.forEach { (id, _, _) -> FirebaseRepository.registerTourist(id, id.replace("_", " ").lowercase().replaceFirstChar { it.uppercase() }) }
        job = scope.launch {
            var tick = 0
            while (isActive) {
                tourists.forEach { (id, pos, _) ->
                    pos[0] += (Random.nextDouble() - 0.5) * 0.0005
                    pos[1] += (Random.nextDouble() - 0.5) * 0.0005
                    val zone = GeofenceManager.checkZones(pos[0], pos[1])
                    val status = if (zone != null) "DANGER" else "SAFE"
                    FirebaseRepository.updateLiveLocation(id, pos[0], pos[1], status)
                    FirebaseRepository.pushLocationHistory(id, pos[0], pos[1])
                    if (status == "DANGER") {
                        FirebaseRepository.updateTouristStatus(id, "DANGER")
                        FirebaseRepository.createAlert(id, "ZONE_ENTRY", "HIGH", pos[0], pos[1])
                    }
                }
                // Simulate SOS every 30 ticks
                if (tick > 0 && tick % 30 == 0) {
                    val (sosId, pos, _) = tourists.random()
                    FirebaseRepository.sendSos(sosId, pos[0], pos[1])
                    delay(10_000); FirebaseRepository.clearSos(sosId)
                }
                tick++; delay(intervalMs)
            }
        }
    }

    fun stop() { job?.cancel(); job = null }
    fun isRunning() = job?.isActive == true
}
