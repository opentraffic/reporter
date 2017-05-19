package org.opentraffic.reporter;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Properties;
import java.util.stream.Stream;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

public class FileProducer  extends Thread {
  private final Producer<String, String> producer;
  private final Properties properties = new Properties();
  private final String topic;
  private final String[] files;

  public FileProducer(String topic, String[] files) {
    properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    properties.put("request.required.acks", "1");
    producer = new KafkaProducer<String, String>(properties);
    this.topic = topic;
    this.files = files;
  }
  
  private void produce(String line) {
    producer.send(new ProducerRecord<String, String>(topic, line));
  }
  
  @Override
  public void run(){
    for(String file : files) {
      try (Stream<String> stream = Files.lines(Paths.get(file))) {
        stream.forEach(this::produce);
      } catch (IOException e) {
        //TODO: log couldnt open file
      }
    }
  }
}
