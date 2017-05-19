package org.opentraffic.reporter;

import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

public class PrintConsumer  extends Thread {
  private final Consumer<String, String> consumer;
  private final Properties properties = new Properties();
  private final List<String> topics;

  public PrintConsumer(List<String> topics) {
    properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
    properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    properties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
    properties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class);
    consumer = new KafkaConsumer<String, String>(properties);
    this.topics = topics;
  }
  
  @Override
  public void run(){
    consumer.subscribe(topics);
    while(true) {
      ConsumerRecords<String, String> records = consumer.poll(Long.MAX_VALUE);
      for(ConsumerRecord<String, String> record : records)
        System.out.println(record.key() + " " + record.value());
    }
  }
}
