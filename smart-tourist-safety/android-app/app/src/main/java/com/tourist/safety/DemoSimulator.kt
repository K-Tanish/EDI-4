package com.tourist.safety

import kotlinx.coroutines.*
import kotlin.random.Random

/**
 * DemoSimulator - simulates multiple tourists for dashboard testing and pipeline event verification.
 * Generates realistic movement and occasionally triggers SOS/geofence alerts.
 * Note: Simulating concurrent tourist events verifies multi-tourist event partitioning
 * and alert latency instrumentation, but does not represent or claim horizontal system scalability.
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
        val baseSimulatedTime = System.currentTimeMillis()
        job = scope.launch {
            var tick = 0
            while (isActive) {
                val simulatedTimestamp = baseSimulatedTime + (tick * intervalMs)
                val tickWallClock = System.currentTimeMillis()

                tourists.forEach { (id, pos, _) ->
                    val tStart = System.currentTimeMillis()
                    pos[0] += (Random.nextDouble() - 0.5) * 0.0005
                    pos[1] += (Random.nextDouble() - 0.5) * 0.0005
                    val zone = GeofenceManager.checkZones(pos[0], pos[1])
                    val status = if (zone != null) "DANGER" else "SAFE"
                    FirebaseRepository.updateLiveLocation(
                        touristId = id,
                        lat = pos[0],
                        lng = pos[1],
                        status = status,
                        simulatedTime = simulatedTimestamp,
                        actualEmittedAtMs = tickWallClock
                    )
                    FirebaseRepository.pushLocationHistory(id, pos[0], pos[1], simulatedTimestamp)
                    if (status == "DANGER") {
                        val latencyMs = (System.currentTimeMillis() - tStart).toDouble()
                        FirebaseRepository.updateTouristStatus(id, "DANGER")
                        FirebaseRepository.createAlert(
                            touristId = id,
                            type = "ZONE_ENTRY",
                            risk = "HIGH",
                            lat = pos[0],
                            lng = pos[1],
                            simulatedTimestamp = simulatedTimestamp,
                            actualEmittedAtMs = System.currentTimeMillis(),
                            processingLatencyMs = latencyMs
                        )
                    }
                }
                // Simulate SOS every 30 ticks
                if (tick > 0 && tick % 30 == 0) {
                    val (sosId, pos, _) = tourists.random()
                    FirebaseRepository.sendSos(sosId, pos[0], pos[1], simulatedTimestamp)
                    delay(10_000); FirebaseRepository.clearSos(sosId)
                }
                tick++; delay(intervalMs)
            }
        }
    }

    fun stop() { job?.cancel(); job = null }
    fun isRunning() = job?.isActive == true
}
